int main() {
    int n = 10;
    int a = 0;
    int b = 1;
    int next = 0;
    int i = 0;

    while (i < n) {
        next = a + b;
        a = b;
        b = next;
        i = i + 1;
    }

    return a;
}
