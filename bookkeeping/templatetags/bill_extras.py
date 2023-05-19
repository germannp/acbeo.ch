from django import template

from ..models import Bill, Purchase

register = template.Library()


@register.simple_tag
def price_of_flight():
    return Bill.PRICE_OF_FLIGHT


@register.simple_tag
def price_of_10_prepaid_flights():
    return Purchase.Items.PREPAID_FLIGHTS.label.split(", Fr. ")[1]


@register.simple_tag
def price_of_day_pass():
    return Purchase.DAY_PASS_PRICE
