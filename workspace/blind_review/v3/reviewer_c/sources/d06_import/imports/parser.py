from decimal import Decimal, InvalidOperation

def parse_row(headers, row):
    if len(headers) != len(row):
        raise ValueError('column count')
    names = [name.strip().lower() for name in headers]
    if len(set(names)) != len(names) or not {'tenant', 'invoice', 'amount'} <= set(names):
        raise ValueError('headers')
    data = dict(zip(names, row))
    tenant, invoice = data['tenant'].strip(), data['invoice'].strip()
    if not tenant or not invoice:
        raise ValueError('empty identity')
    try:
        amount = Decimal(data['amount'].strip())
    except InvalidOperation:
        raise ValueError('amount') from None
    if not amount.is_finite() or amount < 0:
        raise ValueError('amount')
    return {'tenant': tenant, 'invoice': invoice, 'amount': amount}
