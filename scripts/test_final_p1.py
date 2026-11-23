"""Focused synthetic contracts. No official facts, network or operational writes."""
import json,unittest
from unittest.mock import patch
import rag_nlu as n,rag_profile as p,rag_dialogue as d,rag_api as api,rag_turn

class FinalP1(unittest.TestCase):
 def test_correction_is_concept_not_personal_registration(self):
  q='아니, 농업경영체 등록을 물어본 거야.'
  self.assertTrue(n.concept_request(q,{'conversation_topic':'윤작'}))
  self.assertEqual(p.extract(q,d.AREAS,d.CROPS,d.normalized)[0],{})
  for q in ['그 사업에서 등록이 필수야?','올해 독립경영 몇 년까지야?','농업경영체 등록하면 신청 가능해?']:
   self.assertFalse(n.concept_request(q))

 def test_shared_cache_excludes_resolved_followups_and_corrections(self):
  c=n.ConceptCache()
  self.assertTrue(c.key('윤작이 뭐야?'))
  for q in ['윤작에 대해, 후속 질문: 왜?','아니, 농업경영체 등록을 물어본 거야.']:
   self.assertIsNone(c.key(q))

 def test_explicit_finance_concept_replaces_old_topic(self):
  self.assertTrue(n.concept_subject('거치기간은 무슨 뜻이야?'))
  self.assertTrue(n.concept_request('거치기간은 무슨 뜻이야?'))

 def test_new_context_fields_are_bounded_not_model_extracted(self):
  self.assertTrue(p.valid_context({'farm_area_ha':0.1,'export_activity':'no'},d.AREAS))
  for c in [{'farm_area_ha':-1},{'farm_area_ha':float('nan')},{'farm_area_ha':True},{'export_activity':'maybe'}]:
   self.assertFalse(p.valid_context(c,d.AREAS))
  self.assertNotIn('farm_area_ha',n.FIELDS);self.assertNotIn('export_activity',n.FIELDS)
  c={'farm_area_ha':0.1,'export_activity':'yes'}
  self.assertEqual(rag_turn.reset(c,'conversation')['farm_area_ha'],0.1)
  self.assertNotIn('farm_area_ha',rag_turn.reset(c,'profile'))
  self.assertEqual(d.decode(d.PREFIX+json.dumps(c)+d.SEPARATOR+'안녕')[1],c)

 def compare(self,kind,value,context,status='verified'):
  cond={'condition_id':'synthetic','kind':kind,'status':status,'presence':'specified','value':value,'evidence':{'url':'https://www.rda.go.kr/synthetic','location':'synthetic','fact_confirmed':True}}
  doc={'public':{'eligibility':{'conditions':[cond],'logic':{'op':'AND','children':[{'condition_id':'synthetic'}]}}},'record':{'fields':{}}}
  return p.compare(doc,context,lambda x:x.startswith('https://'),d.AREAS)

 def test_approved_cultivated_area_is_not_facility_area(self):
  v={'metric':'cultivated_area','unit':'ha','min':0.1,'max':None,'min_inclusive':True,'max_inclusive':True}
  for context,state in [({},'check'),({'facility_sqm':1000},'check'),({'farm_area_ha':0.09},'mismatch'),({'farm_area_ha':0.1},'match')]:
   r=self.compare('scale',v,context);self.assertEqual(r['structured_state'],state)
  self.assertEqual(self.compare('scale',v,{'farm_area_ha':1},'candidate')['structured_state'],'check')

 def test_export_does_not_infer_activity_from_business_type(self):
  for context,state in [({},'check'),({'applicant':'business'},'check'),({'export_activity':'no'},'mismatch'),({'export_activity':'yes'},'match')]:
   self.assertEqual(self.compare('export_activity',{'required':True},context)['structured_state'],state)

if __name__=='__main__':unittest.main()
