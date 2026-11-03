def user_group_flags(request):
    if request.user.is_authenticated:
        return {
            'is_owner': request.user.groups.filter(name='owner').exists(),
        }
    return {'is_owner': False}


_asset_version = None


def asset_version(request):
    """Content hash of the built bundle, used as ?v= to bust browser caches
    whenever static/dist changes (otherwise users keep running old JS)."""
    global _asset_version
    if _asset_version is None:
        import hashlib
        from pathlib import Path
        from django.conf import settings

        h = hashlib.md5()
        dist = Path(settings.BASE_DIR) / 'static' / 'dist'
        for name in ('bundle.js', 'styles.css'):
            try:
                h.update((dist / name).read_bytes())
            except OSError:
                pass
        _asset_version = h.hexdigest()[:10]
    return {'ASSET_VERSION': _asset_version}
