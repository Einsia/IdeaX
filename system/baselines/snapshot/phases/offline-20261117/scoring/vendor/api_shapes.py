"""Normalize optional API collection fields, retaining original HTTP files."""
def normalized(value):
    if isinstance(value,list):return [normalized(v) for v in value]
    if isinstance(value,dict):
        return {k:([] if v is None and k in ('techniques','supporting_papers','papers') else normalized(v)) for k,v in value.items()}
    return value
