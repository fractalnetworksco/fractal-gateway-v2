from fractal_database_matrix.broker import broker


@broker.task()
async def test_task():
    print("test-task")
    return "test-task"
