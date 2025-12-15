from authlib.integrations.flask_client import OAuth

oauth = OAuth()

def init_oauth(app):
    oauth.init_app(app)

    # Google OAuth (web server flow) :contentReference[oaicite:6]{index=6}
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    # Discord OAuth2 :contentReference[oaicite:7]{index=7}
    oauth.register(
        name="discord",
        client_id=app.config["DISCORD_CLIENT_ID"],
        client_secret=app.config["DISCORD_CLIENT_SECRET"],
        access_token_url="https://discord.com/api/oauth2/token",
        authorize_url="https://discord.com/api/oauth2/authorize",
        api_base_url="https://discord.com/api/",
        client_kwargs={"scope": "identify email"},
    )
