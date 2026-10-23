import copy
import unittest
from price_index.image_list import validate_image_list

# Synthetic transcription; never published as a real offer.
IMAGE = {'format':'image_price_list_v1','list_date':'2020-01-02','currency':'USD','currency_basis':'user_confirmed',
         'source_url':'https://example.com/image','source_name':None,'source_warranty_text':'One Year Warranty',
         'method':'manual_transcription_from_user_image','retailer_verified':False,'notes_ar':['قائمة اختبار اصطناعية'],
         'listings':[{'source_section':'Example','listing_text':'Phone PM Mix 1 Terra','price_usd':123,
                      'availability':None,'condition':None,'model_identity_verified':False}], 'excluded':[]}

class ImageListTests(unittest.TestCase):
    def test_literal_labels_not_manufacturer_identity(self):
        value=validate_image_list(copy.deepcopy(IMAGE))
        self.assertEqual(value['listings'][0]['listing_text'],'Phone PM Mix 1 Terra')
        self.assertIsNone(value['listings'][0]['availability'])

    def test_invalid_prices_duplicates_dates_and_verification_rejected(self):
        bad=[]
        for price in [0,-1,True,'123',float('inf'),float('nan')]:
            v=copy.deepcopy(IMAGE);v['listings'][0]['price_usd']=price;bad.append(v)
        for k,value in [('availability',True),('condition','new'),('model_identity_verified',True)]:
            v=copy.deepcopy(IMAGE);v['listings'][0][k]=value;bad.append(v)
        for k,value in [('currency','LBP'),('list_date','2999-01-01'),('list_date','2026-02-30'),('retailer_verified',True)]:
            v=copy.deepcopy(IMAGE);v[k]=value;bad.append(v)
        v=copy.deepcopy(IMAGE);v['listings'].append(copy.deepcopy(v['listings'][0]));bad.append(v)
        for v in bad:
            with self.subTest(value=v),self.assertRaises(Exception):validate_image_list(v)

    def test_owner_approved_ocr_and_unknown_warranty_are_supported(self):
        value=copy.deepcopy(IMAGE)
        value['method']='ocr_with_user_approval'
        value['source_warranty_text']=None
        validate_image_list(value)
