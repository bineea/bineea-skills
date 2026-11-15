"""验证标签复核的关键约束，不运行完整会议。"""
import copy
import unittest
from apply_speaker_map import apply_decisions


class SpeakerMapTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'id':'a','start':1,'end':4,'speaker':'组1','text':'原文甲'},
                   {'id':'b','start':10,'end':13,'speaker':'组2','text':'原文乙'}]
        self.evidence={'segments':copy.deepcopy(self.rows),'pairs':[
            {'left_id':'a','right_id':'b','similarity':0.8,'overlap_seconds':0}]}
        self.decision={'segment_ids':['b'],'target_speaker':'说话人1','status':'acoustic_match',
                       'basis':'acoustic','evidence_ids':['a','b'],'reason':'测试用声学依据'}

    def test_preserve_source_and_audit(self):
        before=copy.deepcopy(self.rows)
        out,audit=apply_decisions(self.rows,[self.decision],self.evidence)
        self.assertEqual(self.rows,before)
        self.assertEqual(out[1]['original_speaker'],'组2')
        self.assertEqual(out[1]['speaker'],'说话人1')
        for old,new in zip(before,out):
            self.assertEqual((old['text'],old['start'],old['end']),(new['text'],new['start'],new['end']))
        self.assertEqual(audit[0]['segment_id'],'b')

    def test_text_only_cannot_confirm(self):
        d=dict(self.decision,basis='text_only')
        with self.assertRaises(ValueError):
            apply_decisions(self.rows,[d],self.evidence)
        d.update(status='uncertain')
        out,_=apply_decisions(self.rows,[d],self.evidence)
        self.assertIn('待确认',out[1]['speaker'])

    def test_wrong_audio_span_is_rejected(self):
        self.evidence['segments'][1]['start']=9
        with self.assertRaises(ValueError):
            apply_decisions(self.rows,[self.decision],self.evidence)

    def test_duplicate_or_unknown_id_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_decisions(self.rows,[self.decision,self.decision],self.evidence)
        with self.assertRaises(ValueError):
            apply_decisions(self.rows,[dict(self.decision,segment_ids=['missing'])],self.evidence)

    def test_overlapping_audio_is_not_independent_evidence(self):
        self.evidence['pairs'][0]['overlap_seconds']=2
        with self.assertRaises(ValueError):
            apply_decisions(self.rows,[self.decision],self.evidence)


if __name__=='__main__':
    unittest.main()
