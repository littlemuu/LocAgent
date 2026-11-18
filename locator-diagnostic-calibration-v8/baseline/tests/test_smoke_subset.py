import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from locagent_e2e.driver import smoke
class SubsetTests(unittest.TestCase):
 def test_explicit_subset_rejects_unknown_duplicate_empty_before_requests(self):
  for ids in [[],['unknown__repo-1'],['astropy__astropy-14182']*2]:
   with tempfile.TemporaryDirectory() as td,patch('locagent_e2e.transport.LiveTransport.exchange') as exchange:
    with self.assertRaises(PermissionError):smoke(Path(td)/'out','unused','unused',selected_smoke_ids=ids)
    exchange.assert_not_called()
