import json
from pathlib import Path
from price_index.dataset import validate_dataset

if __name__ == '__main__':
    validate_dataset(json.loads(Path('data/phones.json').read_text()))
    from jsonschema import Draft202012Validator, FormatChecker
    schema=json.loads(Path('schemas/status.schema.json').read_text())
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(json.loads(Path('data/status.json').read_text()))
    print('Dataset schema, identity, timestamps, quorum and averages validated')
