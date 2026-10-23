"""Generate one scoped Blogger fragment and the static publication directory."""
from pathlib import Path
import shutil
from price_index.dataset import validate_dataset
import json

ROOT=Path(__file__).resolve().parents[1]
MARKUP='''<section id="leb4tech-index" class="lb4t" lang="ar" dir="rtl" data-url="{url}">
<header><div class="brandmark" dir="ltr">Leb4Tech</div><h1>مؤشر أسعار الهواتف في لبنان</h1><p class="intro">قارن أسعار النسخة نفسها من متاجر لبنانية مستقلة. الأسعار بالدولار الأمريكي USD، دون تقديرات أو تحويل عملات.</p></header>
<div class="filters"><label for="phone-input">ابحث عن هاتف<input id="phone-input" type="search" dir="ltr" maxlength="120" placeholder="Samsung Galaxy أو iPhone" /></label><label for="brand-filter">الشركة<select id="brand-filter"><option value="">كل الشركات</option></select></label><label for="price-filter">الحد الأقصى بالدولار<input id="price-filter" type="number" min="0" step="1" inputmode="decimal" placeholder="دون حد" /></label></div>
<button id="search-btn" type="button">بحث</button><button class="reload" type="button">تحديث البيانات</button>
<div class="notice" role="status" aria-live="polite">جارٍ تحميل الأسعار الموثّقة…</div><p class="source-status muted" aria-live="polite"></p><p class="summary muted"></p><div class="grid" aria-label="قائمة الهواتف"></div>
<footer>المتوسط الحسابي يتطلب متجرين مستقلين على الأقل مع تطابق الموديل والسعة وRAM وSIM والحالة والضمان. الأسعار الأقدم من 6 ساعات تحمل تحذيراً، ولا تُستخدم في متوسط جديد. الأسعار والتوفر قابلان للتغيير؛ راجع صفحة المتجر قبل الشراء. قد تبقى آخر بيانات محفوظة عند انقطاع الاتصال.</footer>
<noscript>يرجى تفعيل JavaScript لعرض بيانات الهواتف.</noscript></section>'''

def build():
    validate_dataset(json.loads((ROOT/'data/phones.json').read_text()))
    css=(ROOT/'assets/app.css').read_text()
    js=(ROOT/'assets/app.js').read_text()
    fragment='<style>\n'+css+'</style>\n'+MARKUP.format(url='https://leb4tech.github.io/mobileprice/data/phones.json')+'\n<script>\n'+js+'\n</script>\n'
    (ROOT/'blogger/page.html').write_text(fragment)
    page='<!DOCTYPE html>\n<html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Leb4Tech | مؤشر أسعار الهواتف</title><link rel="stylesheet" href="assets/app.css"></head><body>\n'+MARKUP.format(url='data/phones.json')+'\n<script src="assets/app.js" defer></script></body></html>\n'
    (ROOT/'index.html').write_text(page)
    output=ROOT/'site'
    output.mkdir(exist_ok=True)
    for directory in ('assets','data','schemas'):
        shutil.copytree(ROOT/directory,output/directory,dirs_exist_ok=True)
    shutil.copyfile(ROOT/'index.html',output/'index.html')
    (output/'.nojekyll').touch()
    (output/'_headers').write_text('/data/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=300\n  X-Content-Type-Options: nosniff\n')

if __name__=='__main__':build()
