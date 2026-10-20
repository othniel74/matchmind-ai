import os
import pytest

# Never load backend/.env during tests, and never call a real model provider.
os.environ['MATCHMIND_SKIP_DOTENV'] = '1'
PROVIDER_VARIABLES = ('MATCHMIND_AI_PROVIDER', 'AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_DEPLOYMENT',
                      'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_API_VERSION',
                      'AZURE_AI_PROJECT_ENDPOINT', 'AZURE_AI_MODEL_DEPLOYMENT_NAME')


@pytest.fixture(autouse=True)
def no_model_provider(monkeypatch):
    for name in PROVIDER_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv('MATCHMIND_INGEST_TOKEN', raising=False)
