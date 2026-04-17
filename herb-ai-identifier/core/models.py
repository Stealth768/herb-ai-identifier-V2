from django.db import models
from django.utils import timezone



class ScannedSpecimen(models.Model):
    """
    The Digital Herbarium Database.
    This model stores every successful AI scan, linking the 
    AI analysis results to the user's uploaded image.
    """
    
    # ── SPECIMEN IDENTITY ─────────────────────────────────────────────────────
    common_name = models.CharField(
        max_length=200, 
        help_text="The primary name identified by Gemini (e.g., Tulsi)"
    )
    scientific_name = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="The botanical Latin name"
    )

    # ── AI METRICS ────────────────────────────────────────────────────────────
    # We store this as a float (e.g., 98.5) for easy math in the progress bars
    confidence = models.FloatField(
        default=0.0,
        help_text="AI confidence score from 0.0 to 100.0"
    )
    
    # ── DATA PROVENANCE ───────────────────────────────────────────────────────
    # Stores the label: 'VAULT + AI' or 'AI LINK'
    reference_img = models.CharField(
        max_length=200, 
        blank=True,
        verbose_name="Data Source Origin"
    )

    # ── PHYSICAL ASSETS ───────────────────────────────────────────────────────
    # Requires 'Pillow' library installed: pip install Pillow
    user_image = models.ImageField(
        upload_to='scans/', 
        blank=True, 
        null=True,
        help_text="The original specimen photo uploaded by the developer"
    )

    # ── ANALYSIS TEXT ─────────────────────────────────────────────────────────
    details = models.TextField(
        blank=True,
        help_text="AI analysis, manual notes, or search context related to this specimen."
    )

    matched_image_url = models.URLField(
        blank=True,
        null=True,
        help_text="Reference image URL fetched from web search for this plant name."
    )

    # ── TEMPORAL DATA ─────────────────────────────────────────────────────────
    timestamp = models.DateTimeField(default=timezone.now)

    ENTRY_TYPES = (
        ('VERIFIED', 'Herbarium Entry'),
        ('NEURAL', 'AI Analysis Result'),
        ('SEARCH', 'Knowledge Search'),
    )
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES, default='NEURAL')

    class Meta:
        # Ensures the most recent scans appear at the top of your Herbarium
        ordering = ['-timestamp']
        verbose_name = "Scanned Specimen"
        verbose_name_plural = "Scanned Specimens"

    def __str__(self):
        """Standardizes the display in the Django Admin panel."""
        return f"{self.common_name} | {self.confidence}% Match | {self.timestamp:%Y-%m-%d}"
    
