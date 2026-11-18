from decimal import Decimal

def tenant_totals(invoices):
    totals = {}
    for invoice in invoices.values():
        tenant = invoice['tenant']
        totals[tenant] = totals.get(tenant, Decimal('0')) + invoice['amount']
    return totals
