int factorial(int n) {
    if (n == 0) {
        return 1;
    }
    return n * factorial(n - 1);
}

int main() {
    return factorial(5); // VM should say in stack "120"
}
