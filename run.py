from app import create_app

app = create_app()


if __name__ == "__main__":
    # Keep the local server single-process. Environment-level Flask debug
    # settings can otherwise start a reloader child, leaving two processes on
    # port 5000 that may serve different revisions during development.
    app.run(debug=False, use_reloader=False)
