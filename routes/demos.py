from flask import Blueprint, Response, stream_with_context
from curl_cffi import requests
from flasgger import swag_from

demos_bp = Blueprint("demos", __name__, url_prefix="/api/v1/download")

@demos_bp.route("/demo/<demo_id>", methods=["GET"])
def download_demo(demo_id: str):
    """
    Download a demo file from HLTV.
    ---
    tags:
      - Demos
    parameters:
      - name: demo_id
        in: path
        type: string
        required: true
        description: The ID of the demo to download.
    responses:
      200:
        description: The demo file stream
      404:
        description: Demo not found
      500:
        description: Internal server error
    """
    target_url = f"https://www.hltv.org/download/demo/{demo_id}"
    
    try:
        # Use curl_cffi to bypass Cloudflare
        # impersonate="safari15_3" worked for match details, using it here too
        # stream=True is critical for large file downloads
        upstream_resp = requests.get(target_url, impersonate="chrome142", stream=True)
        
        if upstream_resp.status_code != 200:
            return {"error": f"Failed to fetch demo: HLTV returned {upstream_resp.status_code}"}, upstream_resp.status_code

        # Generate a flexible filename if Content-Disposition is missing
        filename = f"demo_{demo_id}.rar"
        if "Content-Disposition" in upstream_resp.headers:
             # Basic extraction of filename could optionally be added here, 
             # but forwarding the header is usually sufficient.
             pass

        def generate():
            for chunk in upstream_resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        # Create a streaming response
        response = Response(stream_with_context(generate()), status=upstream_resp.status_code)
        
        # Forward relevant headers
        forward_headers = ['Content-Type', 'Content-Disposition', 'Content-Length']
        for header in forward_headers:
            if header in upstream_resp.headers:
                response.headers[header] = upstream_resp.headers[header]
        
        # Ensure Content-Disposition is set if missing upstream (unlikely for download links but good practice)
        if 'Content-Disposition' not in response.headers:
             response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    except Exception as e:
        return {"error": str(e)}, 500
