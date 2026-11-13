import unittest
from swlocal.process_probe import classify_processes


class StartupGuardTests(unittest.TestCase):
    def row(self,**updates):
        return dict(pid=123,threads=0,age_s=3600,private_bytes=90112,working_bytes=40960,**updates)

    def test_old_zero_thread_record_does_not_block(self):
        self.assertFalse(classify_processes([self.row()])['active_or_unknown'])

    def test_live_process_always_blocks_even_if_small(self):
        row=self.row();row['threads']=1
        self.assertEqual(len(classify_processes([row])['active_or_unknown']),1)

    def test_starting_zero_thread_process_blocks(self):
        row=self.row();row['age_s']=2
        self.assertEqual(len(classify_processes([row])['active_or_unknown']),1)

    def test_unknown_observation_blocks(self):
        for key in ['threads','age_s','private_bytes','working_bytes']:
            row=self.row();row[key]=None
            self.assertEqual(len(classify_processes([row])['active_or_unknown']),1)

    def test_memory_bearing_record_blocks(self):
        for key in ['private_bytes','working_bytes']:
            row=self.row();row[key]=2*1024*1024
            self.assertEqual(len(classify_processes([row])['active_or_unknown']),1)

    def test_malformed_numeric_fields_do_not_count_as_exited(self):
        for value in [float('nan'),-1,True,'unavailable']:
            row=self.row();row['threads']=value
            self.assertEqual(len(classify_processes([row])['active_or_unknown']),1)


if __name__=='__main__':unittest.main()
