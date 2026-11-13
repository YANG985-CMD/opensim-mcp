import importlib.util
from pathlib import Path
import re
import tomllib
import unittest

path=Path(__file__).resolve().parents[1]/'integration/configure_codex.py'
spec=importlib.util.spec_from_file_location('configure_solidworks',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class RenameTests(unittest.TestCase):
    def test_rename_preserves_other_servers_and_nested_values(self):
        source="model='test'\n[mcp_servers.solidworks]\ncommand='python'\nenabled=true\n[mcp_servers.solidworks.env]\nKEY='keep'\n[mcp_servers.matlab]\ncommand='matlab'\n"
        changed=re.sub(r'(?m)^(\[mcp_servers\.)solidworks(?=[.\]])',r'\g<1>'+module.SERVER,source)
        old=tomllib.loads(source);new=tomllib.loads(changed)
        self.assertEqual(old['mcp_servers']['solidworks'],new['mcp_servers']['solidworks-mcp'])
        self.assertEqual(old['mcp_servers']['matlab'],new['mcp_servers']['matlab'])
        self.assertNotIn('solidworks',new['mcp_servers'])
    def test_candidate_is_idempotent_and_preserves_unrelated_prefix(self):
        source="[mcp_servers.solidworks-other]\ncommand='other'\n"
        block=module.block(Path(r'E:\simulink\aanew\SolidWorks输出'))
        changed=module.replacement(source,block)
        self.assertEqual(tomllib.loads(changed)['mcp_servers']['solidworks-other']['command'],'other')
        self.assertEqual(tomllib.loads(module.replacement(changed,block)),tomllib.loads(changed))

if __name__=='__main__':unittest.main()
