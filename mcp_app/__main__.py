from mcp_app import config
from mcp_app.server import build

if __name__ == "__main__":
    build().run(
        transport="http",
        host=config.HOST,
        port=config.PORT,
        path=config.PATH,
    )
