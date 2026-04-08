import os
import uvicorn

from app import app as root_app

app = root_app


def main():
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(root_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
