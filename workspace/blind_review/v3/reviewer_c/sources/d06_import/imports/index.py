def index_invoice(invoices, invoice):
    key = (invoice['tenant'], invoice['invoice'])
    invoices[key] = invoice
