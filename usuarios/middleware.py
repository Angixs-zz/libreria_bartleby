from django.utils.cache import patch_cache_control

class NoCacheMiddleware:
    """
    Middleware that prevents browsers from caching pages for authenticated users.
    This prevents the browser back button from showing cached authenticated pages
    after logout.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # If user is authenticated, prevent caching of the response
        if hasattr(request, 'user') and request.user.is_authenticated:
            patch_cache_control(response, no_cache=True, no_store=True, must_revalidate=True, max_age=0)
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
        return response
