import re

with open('c:/Users/Administrator/Desktop/html_test/WebChat2Local/server/server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to remove from line 662 and all the way to the end of the old HTML block.
# Let's just find where the HTML block ends, which was `</html>\n    """`
# But it's easier to just take everything up to the `serve_dashboard` function and cut out the garbage.

idx = content.find("@app.get(\"/\", response_class=HTMLResponse)")
if idx != -1:
    # get the content up to the end of serve_dashboard
    end_of_serve_dashboard = content.find("serve_dashboard():\n    # Return Dashboard\n    return \"<h1>Studio Dashboard</h1><a href='/studio'>Open Studio</a>\"\n")
    if end_of_serve_dashboard != -1:
        end_idx = end_of_serve_dashboard + len("serve_dashboard():\n    # Return Dashboard\n    return \"<h1>Studio Dashboard</h1><a href='/studio'>Open Studio</a>\"\n")
        
        # After end_idx there is garbage HTML. Let's find the end of it.
        # Just truncate the file at end_idx.
        
        content = content[:end_idx]
        with open('c:/Users/Administrator/Desktop/html_test/WebChat2Local/server/server.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Fixed syntax error")
