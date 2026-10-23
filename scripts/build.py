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
<header><div class="brandmark" dir="ltr">Leb4Tech</div><h1>أسعار الهواتف عالميا</h1><p class="intro">أسعار بيع حالية من متاجر دولية، بالدولار الأمريكي USD. كل سعر مرجع تقريبي مرتبط بمتجر وسوق ونسخة محددة، وقد يتغير عند الشراء.</p></header>
<div class="filters"><label for="phone-input">ابحث عن هاتف<input id="phone-input" type="search" dir="ltr" maxlength="120" placeholder="Samsung Galaxy أو iPhone" /></label><label for="brand-filter">الشركة<select id="brand-filter"><option value="">كل الشركات</option></select></label><label for="price-filter">الحد الأقصى بالدولار<input id="price-filter" type="number" min="0" step="1" inputmode="decimal" placeholder="دون حد" /></label></div>
<label for="market-filter">السوق<select id="market-filter"><option value="">كل الأسواق</option></select></label>
<button id="search-btn" type="button">بحث</button><button class="reload" type="button">تحديث البيانات</button>
<div class="notice" role="status" aria-live="polite">جارٍ تحميل الأسعار الموثّقة…</div><p class="source-status muted" aria-live="polite"></p><p class="summary muted"></p><div class="grid" aria-label="قائمة الهواتف"></div>
<footer>نعرض سعر المتجر عند توفر عرض واحد، ومتوسطا حسابيا عند توفر متجرين مستقلين للنسخة نفسها وفي السوق نفسه. لا نخلط أسعار دول مختلفة ولا نحول العملات. الأسعار بالدولار كما يعلنها المصدر؛ الشحن والضرائب النهائية تحتاج تحقق لدى المتجر. تحمل الأسعار الأقدم من 6 ساعات تحذيرا. لا توجد علاقة بين هذا المؤشر وأسعار الإطلاق التاريخية.</footer>
<section class="image-prices" aria-labelledby="image-title">
<h2 id="image-title">قائمة أسعار من صورة</h2>
<p>أسماء وأسعار منقولة من قائمة مصورة؛ ليست عروض بيع متحققا منها أو متوسط سوق. الأسماء والاختصارات كما وردت في المصدر.</p>
<p class="image-meta muted"></p><p class="image-notice notice" aria-live="polite">جار تحميل القائمة المصورة…</p>
<div class="filters"><label for="image-search">ابحث في القائمة<input id="image-search" type="search" dir="ltr" maxlength="120" placeholder="اسم الهاتف كما في القائمة" /></label><label for="image-brand">القسم في المصدر<select id="image-brand"><option value="">كل الأقسام</option></select></label><label for="image-price">الحد الأقصى بالدولار<input id="image-price" type="number" min="0" step="1" placeholder="دون حد" /></label></div>
<button class="image-reload" type="button">إعادة تحميل القائمة المصورة</button><p class="image-count muted"></p>
<div class="image-table-wrap"><table><thead><tr><th scope="col">القسم</th><th scope="col">الاسم كما في الصورة</th><th scope="col">السعر USD</th></tr></thead><tbody></tbody></table></div>
<p class="image-empty" hidden>لا توجد هواتف مطابقة للبحث.</p></section>
<noscript>يرجى تفعيل JavaScript لعرض بيانات الهواتف.</noscript></section>'''

def build():
    validate_dataset(json.loads((ROOT/'data/global-phones.json').read_text()))
    validate_image_list(json.loads((ROOT/'data/image-prices.json').read_text()))
    css=(ROOT/'assets/app.css').read_text()
    js=(ROOT/'assets/app.js').read_text()+'\n'+(ROOT/'assets/image-prices.js').read_text()
    # Blogger may entity-encode combining marks in inline JavaScript. Emit
    # non-ASCII characters as JS escapes so displayed text remains intact.
    inline_js=''.join(c if ord(c)<128 else c.encode('unicode_escape').decode('ascii') for c in js)
    repository=os.environ.get('GITHUB_REPOSITORY','leb4tech/leb4tech-mobile-prices')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('invalid repository identity')
    owner,name=repository.split('/')
    data_url=f'https://{owner.lower()}.github.io/{name}/data/global-phones.json'
    fragment='<style>\n'+css+'</style>\n'+MARKUP.format(url=data_url)+'\n<script>\n'+inline_js+'\n</script>\n'
    (ROOT/'blogger/page.html').write_text(fragment)
    page='<!DOCTYPE html>\n<html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Leb4Tech | مؤشر أسعار الهواتف</title><link rel="stylesheet" href="assets/app.css"></head><body>\n'+MARKUP.format(url='data/global-phones.json')+'\n<script src="assets/app.js" defer></script><script src="assets/image-prices.js" defer></script></body></html>\n'
    (ROOT/'index.html').write_text(page)
    output=ROOT/'site'
    output.mkdir(exist_ok=True)
    for directory in ('assets','data','schemas'):
        shutil.copytree(ROOT/directory,output/directory,dirs_exist_ok=True)
    shutil.copyfile(ROOT/'index.html',output/'index.html')
    (output/'.nojekyll').touch()
    (output/'_headers').write_text('/data/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=300\n  X-Content-Type-Options: nosniff\n')

if __name__=='__main__':build()
