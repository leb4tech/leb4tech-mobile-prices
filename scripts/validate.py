import json
from pathlib import Path
from price_index.dataset import validate_dataset

if __name__ == '__main__':
    for name in ('phones.json','global-phones.json'):
        validate_dataset(json.loads((Path('data')/name).read_text()))
    from price_index.image_list import validate_image_list
    validate_image_list(json.loads(Path('data/image-prices.json').read_text()))
    from jsonschema import Draft202012Validator, FormatChecker
    schema=json.loads(Path('schemas/status.schema.json').read_text())
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(json.loads(Path('data/status.json').read_text()))
    print('Datasets and image transcription schema, identity, dates, quorum and averages validated')
