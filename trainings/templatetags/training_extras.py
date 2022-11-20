from datetime import date

from django import template

from ..models import Training

register = template.Library()


@register.simple_tag
def training_today():
    return Training.objects.filter(date=date.today()).exists()
