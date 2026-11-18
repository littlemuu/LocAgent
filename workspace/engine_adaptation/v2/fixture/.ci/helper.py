class Box:
    def __init__(self):
        def nested():
            return "中"
        self.value=nested()
