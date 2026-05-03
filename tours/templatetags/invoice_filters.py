from django import template

register = template.Library()


@register.filter
def strip_date_meta(value):
    """Return only the service name part of an InvoiceItem description.
    Descriptions may be encoded as 'service_name|||YYYY-MM-DD|||YYYY-MM-DD|||nights'.
    """
    s = str(value or '')
    return s.split('|||')[0] if '|||' in s else s
