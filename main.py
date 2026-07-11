import uvicorn

from app.config import DATA_DIR, HOST, PORT, validate_runtime_environment


if __name__ == "__main__":
    validate_runtime_environment()
    print(f"PyDebugChat 데이터 경로: {DATA_DIR}")
    print(f"PyDebugChat 접속 주소: http://{HOST}:{PORT}")
    uvicorn.run(
        "app.server:app",
        host=HOST,
        port=PORT,
        reload=False,
    )
