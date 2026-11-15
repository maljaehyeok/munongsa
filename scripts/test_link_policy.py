import unittest,urllib.error
from unittest.mock import patch,MagicMock
from bs4 import BeautifulSoup
import support_link_policy as p,support_guidance_sources as s
class LinkTests(unittest.TestCase):
 def row_check(self):
  r={'source_id':'jeonbuk-buan-official','original_url':'https://www.buan.go.kr/jbares/board/view.buan?dataSid=1','title':'2027년 청년농 지원사업 모집'}
  c={'status':'checked','url':r['original_url'],'title_match':True,'metadata_title_confirmed':True}
  return r,c
 def test_names_links_are_not_a_body_licence(self):
  r,c=self.row_check();v=p.allowed(r,c)
  self.assertEqual(v['scope'],'title_institution_link_only');self.assertFalse(v['body_redistribution']);self.assertFalse(v['attachment_redistribution']);self.assertFalse(v['eligibility_approval'])
 def test_unknown_hosts_failed_links_and_restrictions_remain_blocked(self):
  r,c=self.row_check();c['metadata_link_restricted']=True;self.assertIsNone(p.allowed(r,c))
  c.pop('metadata_link_restricted');c['status']='http_403';self.assertIsNone(p.allowed(r,c))
  c['status']='checked';r['source_id']='new-source';self.assertIsNone(p.allowed(r,c))
 def test_title_must_be_a_name_not_a_body_or_private_information(self):
  r,c=self.row_check();r['title']='가'*181;self.assertIsNone(p.allowed(r,c))
  r['title']='문의 farmer@example.com';self.assertIsNone(p.allowed(r,c))
  r['title']='사업 안내 010-1234-5678';self.assertIsNone(p.allowed(r,c))
 def test_related_notice_does_not_confirm_the_current_title(self):
  self.assertFalse(p.title_check(BeautifulSoup('<h4>다른 공고</h4><p>농업 지원사업 모집</p>','html.parser'),'농업 지원사업 모집',s.norm))
  self.assertTrue(p.title_check(BeautifulSoup('<div class="view_top"><dl><dt>농업 지원사업 모집</dt></dl></div>','html.parser'),'농업 지원사업 모집',s.norm))
 def test_redirects_to_other_hosts_or_http_are_rejected(self):
  robots=MagicMock();robots.can_fetch.return_value=True
  for target in ['https://untrusted.example/post','http://www.mafra.go.kr/post']:
   error=urllib.error.HTTPError('https://www.mafra.go.kr/post',302,'redirect',{'Location':target},None)
   with patch('urllib.request.build_opener') as build:
    build.return_value.open.side_effect=error
    self.assertEqual(s.checked_page('https://www.mafra.go.kr/post',robots)[1],302)
    self.assertEqual(build.return_value.open.call_count,1)
 def test_redirect_path_is_checked_against_robots(self):
  robots=MagicMock();robots.can_fetch.side_effect=[True,False]
  error=urllib.error.HTTPError('https://www.mafra.go.kr/post',302,'redirect',{'Location':'/home/5108/subview.do'},None)
  with patch('urllib.request.build_opener') as build:
   build.return_value.open.side_effect=error
   self.assertEqual(s.checked_page('https://www.mafra.go.kr/post',robots)[1],403)
   self.assertEqual(build.return_value.open.call_count,1)
if __name__=='__main__':unittest.main()
