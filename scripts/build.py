"""Generate one scoped Blogger fragment and the static publication directory."""
from pathlib import Path
import shutil
from price_index.dataset import validate_dataset
from price_index.image_list import validate_image_list
import json
import os
import re

ROOT=Path(__file__).resolve().parents[1]
MARKUP='''<section id="leb4tech-index" class="lb4t" lang="ar" dir="rtl" data-url="{url}">
<header><div class="brandmark" dir="ltr">Leb4Tech</div><h1>أسعار الهواتف</h1><p class="intro">قائمة أسعار الهواتف بالدولار الأمريكي USD.</p></header>
<section class="image-prices" aria-label="قائمة أسعار الهواتف">
<p class="image-meta muted"></p><p class="image-notice notice" role="status" aria-live="polite">جار تحميل الأسعار…</p>
<div class="filters"><label for="image-search">ابحث عن هاتف<input id="image-search" type="search" dir="ltr" maxlength="120" placeholder="Samsung أو iPhone" /></label><label for="image-brand">الشركة<select id="image-brand"><option value="">كل الشركات</option></select></label><label for="image-price">الحد الأقصى بالدولار<input id="image-price" type="number" min="0" step="1" placeholder="دون حد" /></label></div>
<p class="image-count muted"></p>
<div class="image-table-wrap"><table><thead><tr><th scope="col">الشركة</th><th scope="col">الهاتف</th><th scope="col">السعر USD</th></tr></thead><tbody></tbody></table></div>
<p class="image-empty" hidden>لا توجد هواتف مطابقة للبحث.</p></section>
<footer>الأسعار تخص تاريخ القائمة وقد تتغير. تحقق من السعر والتوفر والضمان لدى المتجر قبل الشراء.</footer>
<noscript>يرجى تفعيل JavaScript لعرض الأسعار.</noscript></section>'''


def build():
    validate_dataset(json.loads((ROOT/'data/global-phones.json').read_text()))
    validate_image_list(json.loads((ROOT/'data/image-prices.json').read_text()))
    css=(ROOT/'assets/app.css').read_text()
    js=(ROOT/'assets/image-prices.js').read_text()
    # Blogger may entity-encode combining marks in inline JavaScript. Emit
    # non-ASCII characters as JS escapes so displayed text remains intact.
    inline_js=''.join(c if ord(c)<128 else c.encode('unicode_escape').decode('ascii') for c in js)
    repository=os.environ.get('GITHUB_REPOSITORY','leb4tech/leb4tech-mobile-prices')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('invalid repository identity')
    owner,name=repository.split('/')
    data_url=f'https://{owner.lower()}.github.io/{name}/data/image-prices.json'
    fragment='<style>\n'+css+'</style>\n'+MARKUP.format(url=data_url)+'\n<script>\n'+inline_js+'\n</script>\n'
    (ROOT/'blogger/page.html').write_text(fragment)
    page='<!DOCTYPE html>\n<html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Leb4Tech | مؤشر أسعار الهواتف</title><link rel="stylesheet" href="assets/app.css"></head><body>\n'+MARKUP.format(url='data/image-prices.json')+'\n<script src="assets/image-prices.js" defer></script></body></html>\n'
    (ROOT/'index.html').write_text(page)
    output=ROOT/'site'
    output.mkdir(exist_ok=True)
    for directory in ('assets','data','schemas'):
        shutil.copytree(ROOT/directory,output/directory,dirs_exist_ok=True)
    shutil.copyfile(ROOT/'index.html',output/'index.html')
    (output/'.nojekyll').touch()
    (output/'_headers').write_text('/data/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=300\n  X-Content-Type-Options: nosniff\n')

if __name__=='__main__':build()
