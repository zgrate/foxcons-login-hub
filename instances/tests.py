from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import FoxconsInstance


class FoxconsInstanceModelTestCase(TestCase):
	def test_slug_is_auto_generated(self):
		instance = FoxconsInstance.objects.create(
			name='My Cool Event',
			base_url='https://example.event',
			is_active=True,
		)
		self.assertEqual(instance.slug, 'my-cool-event')

	def test_slug_cannot_be_changed_after_creation(self):
		instance = FoxconsInstance.objects.create(
			name='Stable Slug Event',
			base_url='https://stable.event',
			slug='stable-slug',
			is_active=True,
		)

		instance.slug = 'new-slug'
		with self.assertRaises(ValidationError):
			instance.save()
