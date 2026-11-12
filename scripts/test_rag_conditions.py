"""Condition selection uses existing validation and bypasses question interpretation."""
import unittest
from unittest.mock import patch
import json
import rag_api,rag_dialogue,rag_nlu

class ConditionsTest(unittest.TestCase):
    def test_selection_reuses_validated_context_without_gpt(self):
        context={'region':'부산','farm_region':'부안','age':25,'farm_registered':'no','planned':True}
        q=rag_dialogue.PREFIX+json.dumps(context,ensure_ascii=False)+rag_dialogue.SEPARATOR+'선택한 조건으로 지원사업을 찾아주세요.'
        output=rag_dialogue.response('확인 필요',context)
        with patch.object(rag_api,'load_api_corpus',return_value={'sync_generation':'test','sync_verified':True}),patch.object(rag_api,'decorate_cards'),patch.object(rag_dialogue,'respond',return_value=output) as engine,patch.object(rag_nlu,'interpret',side_effect=AssertionError('no GPT')):
            out=rag_api.local_pipeline(rag_api.validate_input({'question':q}))
        self.assertEqual(out['conversation'],context)
        self.assertEqual(rag_dialogue.decode(engine.call_args.args[0])[1],context)
        self.assertEqual(out['understanding'],'rules')

    def test_invalid_selections_rejected(self):
        for context in ({'age':121},{'farm_registered':'unknown'},{'planned':'true'},{'region':'없는지역'}):
            with self.subTest(context=context),self.assertRaises(ValueError):
                rag_api.validate_input({'question':rag_dialogue.PREFIX+json.dumps(context)+rag_dialogue.SEPARATOR+'검색'})

if __name__=='__main__':unittest.main()
