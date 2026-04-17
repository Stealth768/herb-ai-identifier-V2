import os
import io
import tempfile
import PIL.Image
from difflib import SequenceMatcher
from google import genai

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.conf import settings
from .models import ScannedSpecimen
from .engine import run_inference, fetch_web_image

@csrf_exempt
def send_message(request):
    if request.method == "POST":
        user_text = request.POST.get('message', '').strip()
        image_file = request.FILES.get('image', None)
        
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            content_parts = []
            
            if image_file:
                # Read the image file into a PIL Image
                img = PIL.Image.open(image_file)
                content_parts.append(img)
                if not user_text:
                    user_text = "Analyze this botanical specimen. Provide identification, botanical features, and uses if it's a herb."
            
            if user_text:
                content_parts.append(user_text)
            
            if not content_parts:
                return JsonResponse({'success': False, 'error': 'Please provide a message or image.'})

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=content_parts
            )
            
            return JsonResponse({'success': True, 'response': response.text})
            
        except Exception as e:
            error_str = str(e)
            print(f"Chat error: {error_str}")
            
            # Handle quota exceeded
            if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str or 'quota' in error_str.lower():
                return JsonResponse({
                    'success': False, 
                    'error': 'API quota exceeded. Our service has reached its limit. Please try again in a few moments.'
                })
            
            return JsonResponse({'success': False, 'error': f'AI Link Error: Unable to process request. Please try again.'})
            
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@require_POST
def manual_add(request):
    """Handles the form submission from the Library Modal"""
    name = request.POST.get('common_name')
    image = request.FILES.get('user_image')
    
    matched_image = fetch_web_image(name) if name else None
    ScannedSpecimen.objects.create(
        common_name=name,
        scientific_name='',
        user_image=image,
        reference_img="Manual Herbarium Entry",
        confidence=100.0,
        entry_type='VERIFIED',
        details='Manually added specimen to the herbarium.',
        matched_image_url=matched_image
    )
    return redirect('library')


@require_POST
def scan_herb(request):
    uploaded_file = request.FILES.get('herb_image')

    if not uploaded_file:
        return JsonResponse({'status': 'error', 'message': 'No image file received.'}, status=400)

    allowed_types = ['image/jpeg', 'image/png', 'image/webp']
    if uploaded_file.content_type not in allowed_types:
        return JsonResponse({'status': 'error', 'message': 'Invalid format. Use JPG/PNG/WEBP.'}, status=415)

    try:
        result = run_inference(uploaded_file)
        
        specimen = ScannedSpecimen.objects.create(
            common_name=result.get('name', 'Unknown Specimen'),
            scientific_name=result.get('scientific_name', 'N/A'),
            confidence=result.get('confidence', 0.0),
            reference_img=result.get('source', 'AI LINK'), 
            details=result.get('details', 'No additional botanical data found in vault.'),
            matched_image_url=result.get('matched_image_url'),
            user_image=uploaded_file,
        )

        return JsonResponse({
            'success': True,
            'data': {
                'name': specimen.common_name,
                'scientific': specimen.scientific_name,
                'details': specimen.details,
                'score': specimen.confidence,
                'source': specimen.reference_img,
                'id': specimen.pk
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_GET
def analyzer_view(request):
    specimen_id = request.GET.get('id')
    
    if not specimen_id:
        return render(request, 'core/analyzer.html', {'empty_state': True})

    try:
        specimen = ScannedSpecimen.objects.get(id=specimen_id)
        
        context = {
            'empty_state': False,
            'name': specimen.common_name,
            'scientific_name': specimen.scientific_name,
            'score': specimen.confidence,
            'details': specimen.details,
            'source_label': specimen.reference_img,
            'latest': specimen,
        }
        return render(request, 'core/analyzer.html', context)
    except ScannedSpecimen.DoesNotExist:
        return render(request, 'core/analyzer.html', {'empty_state': True})

@require_GET
def library_view(request):
    specimens = ScannedSpecimen.objects.filter(entry_type='VERIFIED').order_by('-timestamp')
    return render(request, 'core/library.html', {'specimens': specimens})

def library(request):
   
    specimens = ScannedSpecimen.objects.filter(entry_type='VERIFIED').order_by('-timestamp')
    return render(request, 'core/library.html', {'specimens': specimens})


def knowledge_base_view(request):
    kb_path = os.path.join(settings.BASE_DIR, 'data', 'knowledge_base')
    query = request.GET.get('q', '').lower()
    selected_file = request.GET.get('file', None)
    file_content = ""

    all_files = []
    if os.path.exists(kb_path):
        all_files = [f for f in os.listdir(kb_path) if f.endswith('.txt')]

    file_entries = []

    for f_name in all_files:
        excerpt = ''
        similarity = 0
        try:
            with open(os.path.join(kb_path, f_name), 'r', encoding='utf-8') as f:
                text = f.read().strip().replace('\n', ' ')
                excerpt = text[:180] + ('...' if len(text) > 180 else '')
                if query:
                    similarity = int(SequenceMatcher(None, query.lower(), text.lower()).ratio() * 100)
        except OSError:
            excerpt = ''

        file_entries.append({
            'filename': f_name,
            'name': f_name[:-4],
            'excerpt': excerpt,
            'similarity': similarity,
        })

    if query:
        file_entries = sorted(file_entries, key=lambda entry: entry['similarity'], reverse=True)

    selected_similarity = 0
    if selected_file and selected_file in all_files:
        full_path = os.path.join(kb_path, selected_file)
        with open(full_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        if query:
            selected_entry = next((entry for entry in file_entries if entry['filename'] == selected_file), None)
            if selected_entry:
                selected_similarity = selected_entry['similarity']

    context = {
        'files': file_entries,
        'query': query,
        'selected_file': selected_file,
        'file_content': file_content,
        'selected_similarity': selected_similarity,
        'total_docs': len(all_files)
    }
    return render(request, 'core/knowledge_base.html', context)

def ai_history(request):
    history = ScannedSpecimen.objects.filter(entry_type='NEURAL').order_by('-timestamp')
    return render(request, 'core/history.html', {'history': history})
    

def dashboard_view(request):
    kb_path = os.path.join(settings.BASE_DIR, 'data', 'knowledge_base')
    kb_files = []
    if os.path.exists(kb_path):
        kb_files = [f.replace('.txt', '') for f in os.listdir(kb_path) if f.endswith('.txt')]
    
    return render(request, 'core/index.html', {
        'kb_files': kb_files, 
        'user_name': 'Maya',
        'active_scans': ScannedSpecimen.objects.count()
    })

def unified_dashboard(request):
    kb_path = getattr(settings, 'KNOWLEDGE_BASE_DIR', os.path.join(settings.BASE_DIR, 'data', 'knowledge_base'))
    kb_files = []
    if os.path.exists(kb_path):
        kb_files = [f.replace('.txt', '') for f in os.listdir(kb_path) if f.endswith('.txt')]

    query = request.GET.get('q', '')
    search_results = [f for f in kb_files if query.lower() in f.lower()] if query else []

    context = {
        'kb_files': kb_files,
        'query': query,
        'search_results': search_results,
        'user_name': 'Maya',
    }
    return render(request, 'core/unified_dashboard.html', context)

def chat_view(request):
    analysis_id = request.GET.get('analysis_id')
    context = {'user_name': 'Maya'}

    if analysis_id:
        specimen = get_object_or_404(ScannedSpecimen, id=analysis_id)
        context['auto_analyze'] = {
            'name': specimen.common_name,
            'image_url': specimen.user_image.url,
            'confidence': specimen.confidence
        }

    return render(request, 'core/neural_chat.html', context)

@require_POST
def delete_specimen(request, specimen_id):
    """Delete a specimen from the database"""
    try:
        specimen = ScannedSpecimen.objects.get(id=specimen_id)
        specimen.delete()
        return JsonResponse({'success': True, 'message': 'Specimen deleted successfully'})
    except ScannedSpecimen.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Specimen not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def favicon_view(request):
    """Serve favicon.ico to prevent 404 errors"""
    from django.http import FileResponse
    favicon_path = os.path.join(settings.BASE_DIR, 'static', 'icons', 'favicon.ico')
    
    if os.path.exists(favicon_path):
        return FileResponse(open(favicon_path, 'rb'), content_type='image/x-icon')
    
    # Fallback: return a 204 No Content if favicon doesn't exist
    from django.http import HttpResponse
    return HttpResponse(status=204)