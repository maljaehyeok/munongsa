import copy,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import support_guidance_sources as s
class Tests(unittest.TestCase):
 def test_license_requires_exact_source_and_one_type(self):
  r={'source_id':'city','original_url':'https://city.go.kr/post'}
  c={'status':'checked','title_match':True,'url':r['original_url'],'licenses':['4'],'body_sha256':'a'*64}
  with patch.object(s,'source_hosts',return_value={'city':'city.go.kr'}):
   self.assertEqual(s.validate_item(r,c)['scope'],'unchanged_metadata_only')
   with patch.object(s,'NONCOMMERCIAL_METADATA_ONLY',False):self.assertIsNone(s.validate_item(r,c))
   c['licenses']=['1','4'];self.assertIsNone(s.validate_item(r,c))
   c['licenses']=['1'];c['url']='https://other.go.kr/post';self.assertIsNone(s.validate_item(r,c))
 def test_license_parser_does_not_guess_generic_copyright(self):
  from bs4 import BeautifulSoup
  self.assertEqual(s.license_types(BeautifulSoup('<p>Copyright all rights reserved</p>','html.parser')),[])
  self.assertEqual(s.license_types(BeautifulSoup('<img alt="공공누리 제4유형">','html.parser')),['4'])
 def test_duplicate_decisions_are_bound_to_both_articles(self):
  c={'a':{'status':'checked','article':'same applicant period'},'b':{'status':'checked','article':'checked primary'}}
  d={'a':{'primary':'b','article_sha':s.article_sha(c['a']),'primary_article_sha':s.article_sha(c['b'])}}
  s.apply_decisions(c,d);self.assertEqual(c['a']['duplicate_of'],'b')
  c={'a':{'status':'checked','article':'changed'},'b':{'status':'checked','article':'checked primary'}}
  s.apply_decisions(c,d);self.assertTrue(c['a']['decision_changed']);self.assertNotIn('duplicate_of',c['a'])
 def test_condition_plan_needs_source_body_and_existing_approval(self):
  item={'id':'a','url':'https://city.go.kr/post','title':'agriculture','publication':'approved_reference'}
  plan={'id':'a','basis':s.comparison_basis(item),'required_fragments':['verified condition'],'location':'official applicant paragraph',
        'conditions':[{'condition_id':'one','kind':'farm_registration','value':{'registered':True}}]}
  checks={'a':{'status':'checked','title_match':True,'url':item['url'],'article':'verified condition'}}
  now=datetime(2026,11,14,tzinfo=timezone.utc)
  out=s.verified_comparisons({'notices':[item]},[plan],checks,now)
  self.assertFalse(out['a']['complete']);self.assertTrue(out['a']['conditions'][0]['evidence']['fact_confirmed'])
  checks['a']['article']='changed';self.assertFalse(s.verified_comparisons({'notices':[item]},[plan],checks,now))
  item['publication']='review';self.assertFalse(s.verified_comparisons({'notices':[item]},[plan],checks,now))
if __name__=='__main__':unittest.main()
