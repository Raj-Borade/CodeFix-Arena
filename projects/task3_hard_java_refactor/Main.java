// No package declaration intentionally for runtime execution in sandbox
public class Main {
    public static void main(String[] args) {
        CalculatorService service = new CalculatorService();
        int result = service.add(10, 5);
        System.out.println(ResultFormatter.format(result));
    }
}