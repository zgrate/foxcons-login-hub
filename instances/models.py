from django.db import models
from django.utils.text import slugify
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError


hex_color_validator = RegexValidator(
    regex=r'^#[0-9A-Fa-f]{6}$',
    message='Use a valid HEX color like #ef4444',
)

class FoxconsInstance(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    base_url = models.URLField(unique=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    icon = models.ImageField(
        upload_to='instance_icons/',
        blank=True,
        null=True,
        help_text='Optional icon displayed on the login page event selector (recommended: square, min 64×64 px).',
    )
    theme_primary = models.CharField(
        max_length=7,
        default='#fca5a5',
        validators=[hex_color_validator],
        help_text='Primary motif color for this event (HEX), used in hero gradients.',
    )
    theme_secondary = models.CharField(
        max_length=7,
        default='#ef4444',
        validators=[hex_color_validator],
        help_text='Secondary motif color for this event (HEX), used for buttons and accents.',
    )
    theme_text = models.CharField(
        max_length=7,
        default='#2b0a0a',
        validators=[hex_color_validator],
        help_text='Text color used on bright hero sections for this event motif (HEX).',
    )

    class Meta:
        ordering = ['display_order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if self.pk:
            previous_slug = (
                FoxconsInstance.objects.filter(pk=self.pk)
                .values_list('slug', flat=True)
                .first()
            )
            if previous_slug and previous_slug != self.slug:
                raise ValidationError('Slug cannot be changed after creation.')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
