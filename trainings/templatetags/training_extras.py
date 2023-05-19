from django import template
from django.utils import timezone

from ..models import Training

register = template.Library()


@register.simple_tag
def training_today():
    return Training.objects.filter(date=timezone.now().date()).exists()
