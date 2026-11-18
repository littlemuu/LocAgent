from .parser import parse_row
from .index import index_invoice
from .totals import tenant_totals

def import_rows(headers, rows):
    invoices = {}
    errors = []
    for number, row in enumerate(rows, 1):
        try:
            invoice = parse_row(headers, row)
            index_invoice(invoices, invoice)
        except ValueError:
            errors.append(number)
    return {'totals': tenant_totals(invoices), 'errors': errors}
