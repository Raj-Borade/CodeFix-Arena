class DebugTasks:

    @staticmethod
    def get_tasks():

        return [

            {
                "id": 1,
                "language": "python",
                "buggy_code": """
def add(a,b)
    return a+b
""",
                "expected_fix": "syntax_error"
            },

            {
                "id": 2,
                "language": "python",
                "buggy_code": """
def multiply(a,b):
return a*b
""",
                "expected_fix": "indentation_error"
            },

            {
                "id": 3,
                "language": "java",
                "buggy_code": """
public class Test {
    public static void main(String[] args) {
        System.out.println("Hello"
    }
}
""",
                "expected_fix": "missing_parenthesis"
            }

        ]