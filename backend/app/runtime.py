"""Honest deployment boundary for controls that are still local-only."""
import os


class RuntimeConfigurationError(RuntimeError):
    pass


def validate_runtime():
    mode=os.getenv('MATCHMIND_ENV','local').strip().lower()
    if mode not in {'local','test','demo','production'}:
        raise RuntimeConfigurationError('Unknown MATCHMIND_ENV. Use local, test or demo; production is release-blocked.')
    if mode=='production':
        raise RuntimeConfigurationError(
            'Production release blocked: managed identity, tenant isolation, external delivery controls '
            'and measured release evaluations are not implemented or verified. See docs/PRODUCTION_READINESS_AUDIT.md.')
    return mode


# A public demo is read-only: these switches are forced off whatever the environment says.
DEMO_DISABLED = ('MATCHMIND_CORRECTIONS_ENABLED', 'MATCHMIND_REVIEW_ENABLED', 'MATCHMIND_PUBLICATION_ENABLED',
                 'MATCHMIND_RESEARCH_ENABLED', 'GRAPH_REBUILD_ENABLED')


def apply_demo_restrictions(mode):
    if mode != 'demo':
        return
    for name in DEMO_DISABLED:
        os.environ[name] = 'false'
    os.environ.pop('MATCHMIND_INGEST_TOKEN', None)


def is_demo():
    return os.getenv('MATCHMIND_ENV', 'local').strip().lower() == 'demo'


class RuntimeBoundary:
    """Also deny requests when an ASGI host explicitly disables lifespan startup."""
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type'] in {'http','websocket'}:
            try:validate_runtime()
            except RuntimeConfigurationError:
                if scope['type']=='websocket':
                    await send({'type':'websocket.close','code':1008,'reason':'Runtime configuration is release-blocked.'})
                else:
                    from starlette.responses import JSONResponse
                    await JSONResponse({'detail':'Runtime configuration is release-blocked.','production_ready':False},status_code=503,headers={'Cache-Control':'no-store'})(scope,receive,send)
                return
        await self.app(scope,receive,send)
