"""Pinned local SPECTER2 base + proximity adapter; never downloads at runtime."""
from pathlib import Path
import hashlib
import json
import os

ENVIRONMENT = Path(__file__).resolve().parent


class LocalSpecter2:
    def __init__(self, threads=8):
        import torch
        from transformers import AutoTokenizer
        from adapters import AutoAdapterModel

        self.torch = torch
        self.manifest = json.loads((ENVIRONMENT / 'models_manifest.json').read_text())
        for item in self.manifest['files']:
            path = Path(item['path'])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise RuntimeError('Pinned SPECTER2 file changed: ' + str(path))
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        torch.set_num_threads(threads)
        base = ENVIRONMENT / 'models/allenai--specter2_base'
        adapter = ENVIRONMENT / 'models/allenai--specter2'
        self.tokenizer = AutoTokenizer.from_pretrained(str(base), local_files_only=True)
        self.model = AutoAdapterModel.from_pretrained(str(base), local_files_only=True)
        self.model.load_adapter(str(adapter), load_as='specter2', set_active=True)
        self.model.to('cpu').eval()
        if str(self.model.active_adapters) != 'Stack[specter2]':
            raise RuntimeError('The official proximity adapter is not active')

    def encode(self, papers, batch_size=8):
        vectors = []
        for start in range(0, len(papers), batch_size):
            batch = papers[start:start + batch_size]
            texts = [paper['title'] + self.tokenizer.sep_token + (paper.get('abstract') or '') for paper in batch]
            inputs = self.tokenizer(texts, padding=True, truncation=True, return_tensors='pt',
                                    return_token_type_ids=False, max_length=512)
            with self.torch.inference_mode():
                values = self.model(**inputs).last_hidden_state[:, 0, :].cpu()
            if values.shape != (len(batch), 768) or not self.torch.isfinite(values).all():
                raise RuntimeError('SPECTER2 returned invalid vectors')
            vectors.append(values)
        return self.torch.cat(vectors).numpy() if vectors else self.torch.empty((0, 768)).numpy()
