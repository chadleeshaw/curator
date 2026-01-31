# Python Best Practices Guide
## Procedural Programming for High-Quality, Organized, and Human-Readable Code

> This guide provides essential best practices for Python procedural programming, with a focus on AI, data science, and machine learning applications. Following these guidelines ensures code that is functional, maintainable, scalable, and understandable.

---

## Table of Contents
1. [Naming Conventions](#naming-conventions)
2. [Spacing and Bracketing](#spacing-and-bracketing)
3. [Using Literals](#using-literals)
4. [Variables and Scope](#variables-and-scope)
5. [Boolean Expressions](#boolean-expressions)
6. [Branching (If/Else)](#branching-ifelse)
7. [Loops](#loops)
8. [Modularity & Functions](#modularity--functions)
9. [DRY Principle](#dry-principle)
10. [One-and-Only-One Task](#one-and-only-one-task)
11. [Function Length](#function-length)
12. [Driver Files](#driver-files)
13. [Libraries and Frameworks](#libraries-and-frameworks)
14. [Exception Handling](#exception-handling)
15. [Documentation](#documentation)
16. [Testing](#testing)

---

## Naming Conventions

### General Principles
- **Use descriptive names**: Names should be meaningful and convey purpose
- **Follow PEP 8**: Adhere to Python's official style guide
- **Comment complex sections**: Explain logic that isn't immediately obvious

### Bad vs Good Examples
```python
# Bad practice
x = 25
variable = "Hello"

# Good practice
temperature = 25
greeting_message = "Hello"
```

### Counter Variables
Accepted single-letter names for counters: `i`, `j`, `k`

```python
for i in range(10):
    print(i)

# Nested loops
for i in range(5):
    for j in range(3):
        print(i, j)
```

### Snake Case Convention
Use `snake_case` for functions and variables in procedural programming:

```python
def calculate_grade(scores):
    total = sum(scores)
    count = len(scores)
    grade = total / count
    return grade
```

### Camel Case Convention
Use `camelCase` primarily for object-oriented programming:

```python
class Student:
    def __init__(self, name, grade):
        self.name = name
        self.grade = grade
    
    def displayStudentInfo(self):
        print(f"Student Name: {self.name}, Grade: {self.grade}")
```

### Constants
Use `UPPER_CASE_WITH_UNDERSCORES` for constants:

```python
MAX_ITERATIONS = 100
LEARNING_RATE = 0.01

def train_model(data):
    for iteration in range(MAX_ITERATIONS):
        data = data * LEARNING_RATE
    return data
```

---

## Spacing and Bracketing

### Proper Indentation
Indentation highlights hierarchical structure and logical blocks:

```python
def preprocess_data(data):
    if data is not None:
        for item in data:
            item = item.strip()
            print(item)
    else:
        print("No data to process")
```

### Use Brackets for Logical Grouping
```python
# Dictionaries
model_params = {
    'learning_rate': 0.01,
    'n_estimators': 100,
    'max_depth': 10
}

# List comprehensions
squared_numbers = [x**2 for x in range(10)]
```

### Consistent Bracketing
Maintain the same style throughout your codebase:

```python
def evaluate_model(model, test_data):
    predictions = model.predict(test_data)
    accuracy = sum(predictions == test_data['labels']) / len(test_data)
    return accuracy
```

### Spaces, Not Tabs
- **Always use spaces** instead of tabs for indentation
- **Configure your editor** to replace tabs with 4 spaces
- **Four spaces per indent** is the Python standard

```python
def load_data(file_path):
    with open(file_path, 'r') as file:
        data = file.read()
    return data
```

---

## Using Literals

### Avoid Direct Literals
Using literals directly leads to:
- Poor readability
- Difficult maintenance
- Poor reusability

### Use Global Constants
For values used across multiple scopes:

```python
# Global constants
LEARNING_RATE = 0.01
MAX_ITERATIONS = 100
THRESHOLD = 0.5

def preprocess_data(data):
    return [item for item in data if item > THRESHOLD]

def train_model(data):
    model = SomeModel(
        learning_rate=LEARNING_RATE,
        max_iterations=MAX_ITERATIONS
    )
    model.fit(data)
    return model
```

### Use Local Constants
For values used only within a function:

```python
def evaluate_model(predictions, labels):
    # Local constant
    THRESHOLD = 0.5
    
    predictions_binary = [1 if pred > THRESHOLD else 0 for pred in predictions]
    accuracy = sum([1 for pred, label in zip(predictions_binary, labels) 
                   if pred == label]) / len(labels)
    return accuracy
```

### Exceptions
Acceptable literal values: **-1, 0, 1**

```python
# Using 0 to start a loop
for i in range(10):
    print(i)

# Using -1 as an error condition
def find_element(element, lst):
    try:
        index = lst.index(element)
    except ValueError:
        index = -1
    return index
```

---

## Variables and Scope

### What is a Variable?
A named location in memory for storing data values. Python determines type automatically.

```python
x = 10              # Integer
name = "Alice"      # String
pi = 3.1416         # Float
```

### Local Scope
Variables defined inside a function exist only within that function:

```python
def calculate_area(radius):
    pi = 3.1416  # Local variable
    area = pi * (radius ** 2)
    return area

# print(pi)  # Would raise NameError
```

**Characteristics:**
- Exist only inside their function
- Cannot be accessed outside the function
- Different functions can have same-named variables

### Global Scope
Variables declared outside all functions, accessible everywhere:

```python
count = 0  # Global variable

def increment():
    global count
    count += 1
```

**⚠️ Avoid Global Variables**

Use global **constants** instead:

```python
PI = 3.1416  # Global constant

def calculate_area(radius):
    return PI * (radius ** 2)
```

### Intermediate Variables
Temporary variables for storing values:

```python
# Without intermediate variable (preferred when simple)
def compute_total_cost(price, quantity):
    return price * quantity

# With intermediate variable (when it improves readability)
def compute_complex_value(a, b, c):
    intermediate_result = (a * b) + (b * c)
    final_result = intermediate_result * 2
    return final_result
```

**Use intermediate variables only when they:**
- Significantly improve readability
- Prevent recalculating complex expressions
- Give meaningful names to parts of calculations

### Best Practices
1. **Use local variables** over global ones
2. **Minimize intermediate variables** - use only when necessary
3. **Use global constants** instead of mutable global variables
4. **Pass values to functions** via parameters

---

## Boolean Expressions

### Limit Compound Expressions
Keep to **3-4 expressions maximum**:

```python
# Simple and readable
if age > 18 and income > 50000 and has_good_credit:
    approve_loan()
```

### Refactor Long Expressions
When expressions extend to **5+ conditions**, break them down:

```python
# Too long (not preferred)
if age > 18 and income > 50000 and has_good_credit and not has_criminal_record and employment_status == 'employed':
    approve_loan()

# Refactored (preferred)
def is_eligible_for_loan(age, income, has_good_credit, has_criminal_record, employment_status):
    is_adult = age > 18
    has_sufficient_income = income > 50000
    has_no_criminal_record = not has_criminal_record
    is_employed = employment_status == 'employed'
    
    return is_adult and has_sufficient_income and has_good_credit and has_no_criminal_record and is_employed

if is_eligible_for_loan(age, income, has_good_credit, has_criminal_record, employment_status):
    approve_loan()
```

### Use Helper Functions
For **6+ boolean conditions**, create helper functions:

```python
def is_adult(age):
    return age > 18

def has_sufficient_income(income):
    return income > 50000

def has_no_criminal_record(record):
    return not record

def is_employed(status):
    return status == 'employed'

def is_eligible_for_loan(age, income, has_good_credit, has_criminal_record, employment_status):
    return (is_adult(age) and
            has_sufficient_income(income) and
            has_good_credit and
            has_no_criminal_record(has_criminal_record) and
            is_employed(employment_status))
```

---

## Branching (If/Else)

### Limit Nesting
Keep nesting to **2-3 levels maximum**:

```python
# Acceptable
def evaluate_performance(metrics):
    if metrics['accuracy'] > 0.8:
        if metrics['precision'] > 0.7:
            if metrics['recall'] > 0.7:
                return "Model is performing well"
    return "Model needs improvement"
```

### Avoid Deep Nesting
**4+ levels** indicates overly complex logic - refactor:

```python
# Too complex (avoid)
def complex_logic(a, b, c, d):
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    return "All positive"
    return "Not all positive"

# Refactored (preferred)
def is_positive(x):
    return x > 0

def evaluate_conditions(a, b, c, d):
    if is_positive(a) and is_positive(b) and is_positive(c) and is_positive(d):
        return "All positive"
    return "Not all positive"
```

### Use If/Elif/Else Chains
These can be as long as necessary:

```python
def classify_score(score):
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"
```

---

## Loops

### Limit Loop Nesting
Keep to **2-3 levels maximum**:

```python
# Preferred
def process_data(matrix):
    for row in matrix:
        for item in row:
            print(item)
```

### Avoid Purposeful Infinite Loops
Never use `while True:` - there's always a better way:

```python
# Avoid
while True:
    # Do something
    pass

# Preferred
condition = True
while condition:
    # Do something
    condition = check_condition()
```

### Use Determinant Loops
Use `for` loops when you know the number of iterations:

```python
for i in range(10):
    print(i)
```

### Use Indeterminate Loops
Use `while` loops when iterations are unknown:

```python
while some_condition:
    # Do something
    update_condition()
```

### Avoid Break and Continue
These can indicate faulty logic and disrupt optimization:

```python
# Avoid
for i in range(10):
    if i == 5:
        break
    print(i)

# Preferred
for i in range(10):
    if i != 5:
        print(i)
```

### Minimize If Statements Inside Loops
```python
# Avoid
for i in range(10):
    if i % 2 == 0:
        print(i)

# Preferred
for i in range(0, 10, 2):
    print(i)
```

---

## Modularity & Functions

### Importance
> A modularized program organizes each task within its own function.

Modularity enhances:
- **Readability**: Easier to understand code structure
- **Maintainability**: Changes are localized
- **Reusability**: Functions can be used in multiple places

### Functions as Building Blocks
- Each function should perform **one specific task**
- Programs should be **collections of functions**
- Functions can call other functions

---

## DRY Principle

### Don't Repeat Yourself
> Every piece of knowledge must have a single, unambiguous, authoritative representation within a system.

Code repetition leads to:
- More errors
- Harder maintenance
- Less reliable code

### Encapsulate Repeated Logic
```python
# Repeated code (avoid)
data = pd.read_csv('data.csv')
data = data.fillna(0)
data = data[data >= 0]

more_data = pd.read_csv('more_data.csv')
more_data = more_data.fillna(0)
more_data = more_data[more_data >= 0]

# DRY approach (preferred)
def preprocess_data(data):
    data = data.fillna(0)
    data = data[data >= 0]
    return data

data = preprocess_data(pd.read_csv('data.csv'))
more_data = preprocess_data(pd.read_csv('more_data.csv'))
```

### Use Loops for Repetition
```python
# Repeated code (avoid)
print(data[0])
print(data[1])
print(data[2])

# Using loop (preferred)
for item in data:
    print(item)
```

### Benefits
1. **Reduced errors**: Centralized logic minimizes inconsistencies
2. **Easier maintenance**: Update in one place
3. **Improved collaboration**: Clear, modular code
4. **Enhanced performance**: Reusable, optimized functions

### Avoid exit() or quit()
Don't use `exit()` or `quit()` except possibly at the very end (and even then it's usually unnecessary).

---

## One-and-Only-One Task

### Single Responsibility Principle
> A function should perform only one specific task.

**Benefits:**
- **Readability**: Clear, focused purpose
- **Reusability**: Can be used in multiple contexts
- **Testing**: Easier to write unit tests
- **Debugging**: Simpler to isolate bugs
- **Collaboration**: Team members can work independently

### Data Preprocessing Example
```python
import pandas as pd
from sklearn.preprocessing import StandardScaler

# Separate functions for each task
def handle_missing_values(data):
    return data.fillna(0)

def normalize_data(data):
    scaler = StandardScaler()
    return pd.DataFrame(scaler.fit_transform(data), columns=data.columns)

def encode_categorical(data):
    return pd.get_dummies(data)

# Main orchestration function
def preprocess_data(data):
    data = handle_missing_values(data)
    data = normalize_data(data)
    data = encode_categorical(data)
    return data
```

### Model Training Example
```python
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error

# Each task has its own function
def split_data(features, target):
    return train_test_split(features, target, test_size=0.2, random_state=42)

def train_model(X_train, y_train):
    model = LinearRegression()
    model.fit(X_train, y_train)
    return model

def evaluate_model(model, X_test, y_test):
    predictions = model.predict(X_test)
    mse = mean_squared_error(y_test, predictions)
    return mse

# Pipeline function orchestrates
def model_training_pipeline(features, target):
    X_train, X_test, y_train, y_test = split_data(features, target)
    model = train_model(X_train, y_train)
    mse = evaluate_model(model, X_test, y_test)
    return model, mse
```

---

## Function Length

### Keep Functions Concise
Functions should be **no more than a couple dozen lines** (typically under 24 lines).

### Too Long Example
```python
# This function is too long - it does too much
def process_and_train_model(data):
    # Handle missing values
    data = data.fillna(0)
    
    # Remove negative values
    data = data[data >= 0]
    
    # Normalize numerical features
    scaler = StandardScaler()
    data[['age', 'salary']] = scaler.fit_transform(data[['age', 'salary']])
    
    # Encode categorical variables
    encoder = LabelEncoder()
    data['gender'] = encoder.fit_transform(data['gender'])
    
    # Split data
    features = data[['age', 'salary', 'gender']]
    target = data['target']
    X_train, X_test, y_train, y_test = train_test_split(
        features, target, test_size=0.2, random_state=42
    )
    
    # Train model
    model = LinearRegression()
    model.fit(X_train, y_train)
    
    # Make predictions
    predictions = model.predict(X_test)
    
    # Calculate MSE
    mse = mean_squared_error(y_test, predictions)
    print(f"Model Mean Squared Error: {mse}")
    
    return model, mse
```

### Refactored Example
```python
def preprocess_data(data):
    data = data.fillna(0)
    data = data[data >= 0]
    return data

def normalize_features(data, features):
    scaler = StandardScaler()
    data[features] = scaler.fit_transform(data[features])
    return data

def encode_categorical(data, columns):
    encoder = LabelEncoder()
    for column in columns:
        data[column] = encoder.fit_transform(data[column])
    return data

def split_data(data, target_column, test_size=0.2, random_state=42):
    features = data.drop(columns=[target_column])
    target = data[target_column]
    return train_test_split(features, target, test_size=test_size, random_state=random_state)

def train_model(X_train, y_train):
    model = LinearRegression()
    model.fit(X_train, y_train)
    return model

def evaluate_model(model, X_test, y_test):
    predictions = model.predict(X_test)
    mse = mean_squared_error(y_test, predictions)
    return mse

# Orchestration function
def process_and_train_model(data):
    data = preprocess_data(data)
    data = normalize_features(data, ['age', 'salary'])
    data = encode_categorical(data, ['gender'])
    X_train, X_test, y_train, y_test = split_data(data, 'target')
    model = train_model(X_train, y_train)
    mse = evaluate_model(model, X_test, y_test)
    print(f"Model Mean Squared Error: {mse}")
    return model, mse
```

---

## Driver Files

### Key Principles
1. **One driver file**: Single entry point (`main.py`)
2. **Single main() function**: Driver file contains only `main()`
3. **Code directly in driver**: Acceptable for simple scripts
4. **Length exemption**: Driver functions can be longer than 24 lines
5. **No repeated code**: Still follow DRY principle
6. **Use constants**: Define literals as constants

### Example Driver File
```python
# Define constants
DATA_FILE = 'data.csv'
MODEL_FILE = 'model.pkl'

def main():
    import pandas as pd
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_squared_error
    from joblib import load, dump
    
    # Load data
    data = pd.read_csv(DATA_FILE)
    
    # Preprocess data
    data = preprocess_data(data)
    
    # Split data
    features = data[['age', 'salary']]
    target = data['target']
    
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        features, target, test_size=0.2, random_state=42
    )
    
    # Train model
    model = LinearRegression()
    model.fit(X_train, y_train)
    
    # Save model
    dump(model, MODEL_FILE)
    
    # Evaluate
    predictions = model.predict(X_test)
    mse = mean_squared_error(y_test, predictions)
    print(f"Model Mean Squared Error: {mse}")

def preprocess_data(data):
    data = data.fillna(0)
    data = data[data >= 0]
    return data

if __name__ == "__main__":
    main()
```

---

## Libraries and Frameworks

> Leverage Python's rich ecosystem to avoid reinventing the wheel.

### Essential Libraries
- **[NumPy](https://numpy.org/)**: Numerical operations
- **[Pandas](https://pandas.pydata.org/)**: Data manipulation
- **[scikit-learn](https://scikit-learn.org/)**: Machine learning
- **[TensorFlow](https://www.tensorflow.org/)**: Deep learning
- **[PyTorch](https://pytorch.org/)**: Deep learning

---

## Exception Handling

### Why It's Important
- **Data integrity**: Prevents data corruption
- **Model training**: Manages errors gracefully
- **User experience**: Provides meaningful feedback
- **Debugging**: Helps identify issues quickly

### Basic Structure
```python
def divide(a, b):
    try:
        result = a / b
    except ZeroDivisionError as e:
        print(f"Error: Cannot divide by zero. {e}")
        result = None
    except TypeError as e:
        print(f"Error: Invalid input type. {e}")
        result = None
    else:
        print("Division successful")
    finally:
        print("Execution complete")
    return result
```

### Data Loading Example
```python
import pandas as pd

def load_data(file_path):
    try:
        data = pd.read_csv(file_path)
    except FileNotFoundError as e:
        print(f"Error: {e}. Please check the file path.")
        data = None
    except pd.errors.ParserError as e:
        print(f"Error: {e}. File might be corrupted or not CSV format.")
        data = None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        data = None
    else:
        print("Data loaded successfully")
    finally:
        print("Data loading attempt finished")
    return data
```

### Model Training Example
```python
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split

def train_model(X, y):
    try:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
        model = LinearRegression()
        model.fit(X_train, y_train)
    except ValueError as e:
        print(f"ValueError: {e}. Check your data for inconsistencies.")
        model = None
    except MemoryError as e:
        print(f"MemoryError: {e}. Dataset might be too large.")
        model = None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        model = None
    else:
        print("Model trained successfully")
    finally:
        print("Model training attempt finished")
    return model
```

### Best Practices
1. **Catch specific exceptions** rather than generic `Exception`
2. **Provide meaningful messages** to help understand issues
3. **Use logging** to record exceptions for later analysis
4. **Fail gracefully** and clean up resources
5. **Implement retries** for transient errors

---

## Documentation

### Docstrings
Document functions, classes, and modules directly in code:

```python
def load_data(file_path):
    """
    Load data from a CSV file.
    
    Parameters:
    -----------
    file_path : str
        The path to the CSV file to be loaded.
    
    Returns:
    --------
    DataFrame
        A pandas DataFrame containing the loaded data.
    
    Raises:
    -------
    FileNotFoundError
        If the file does not exist.
    pd.errors.ParserError
        If the file is not in the correct format.
    Exception
        For any other unexpected errors.
    """
    try:
        data = pd.read_csv(file_path)
    except FileNotFoundError as e:
        print(f"Error: {e}. Please check the file path.")
        data = None
    except pd.errors.ParserError as e:
        print(f"Error: {e}. File might be corrupted.")
        data = None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        data = None
    else:
        print("Data loaded successfully")
    finally:
        print("Data loading attempt finished")
    return data
```

### Docstring Components
1. **Summary line**: Brief description of function purpose
2. **Parameters section**: Name, type, and description of each parameter
3. **Returns section**: Type and description of return value
4. **Raises section**: Exceptions that might be raised

### README Files
Create a comprehensive `README.md`:

```markdown
# Project Title

## Overview
A brief description of what the project does, its goals, and scope.

## Features
- Feature 1
- Feature 2
- Feature 3

## Installation

### Prerequisites
List prerequisites such as Python version, required libraries, etc.

```bash
pip install -r requirements.txt
```

## Usage
Instructions on how to use the project, with examples.

```bash
python main.py --input data.csv --output results.csv
```

## Testing
Instructions for running tests.

## Contributing
Guidelines for contributing to the project.

## License
License information.
```

---

## Testing

### Why Test?
- **Ensures correctness**: Code behaves as expected
- **Prevents bugs**: Catches issues early
- **Facilitates changes**: Refactor with confidence
- **Documentation**: Tests show how code should work

### Write Unit Tests
```python
import unittest

def calculate_mean(numbers):
    """
    Calculate the mean of a list of numbers.
    
    Parameters:
    -----------
    numbers : list of float
        A list of numerical values.
    
    Returns:
    --------
    float
        The mean of the numbers.
    
    Raises:
    -------
    ValueError
        If the input list is empty.
    """
    if not numbers:
        raise ValueError("The list is empty")
    return sum(numbers) / len(numbers)

class TestCalculateMean(unittest.TestCase):
    
    def test_mean_of_positive_numbers(self):
        self.assertEqual(calculate_mean([1, 2, 3, 4, 5]), 3.0)
    
    def test_mean_of_negative_numbers(self):
        self.assertEqual(calculate_mean([-1, -2, -3]), -2.0)
    
    def test_mean_of_mixed_numbers(self):
        self.assertEqual(calculate_mean([-1, 0, 1]), 0.0)
    
    def test_empty_list(self):
        with self.assertRaises(ValueError):
            calculate_mean([])
    
    def test_single_element(self):
        self.assertEqual(calculate_mean([5]), 5.0)

if __name__ == '__main__':
    unittest.main()
```

### Test Edge Cases
Ensure functions handle all scenarios:
- Empty inputs
- Very large/small numbers
- Duplicate values
- Invalid inputs
- Boundary conditions

### Best Practices for Testing
1. **Isolation**: Each test should be independent
2. **Descriptive names**: Indicate what's being tested
3. **Comprehensive coverage**: Test all scenarios including edge cases
4. **Use assertions**: Check for expected outcomes
5. **Automate testing**: Integrate into development workflow

---

## Summary Checklist

### Naming
- ✅ Use descriptive, meaningful names
- ✅ Follow snake_case for functions/variables
- ✅ Use UPPER_CASE for constants
- ✅ Single letters only for counters (i, j, k)

### Code Structure
- ✅ Use 4 spaces (not tabs) for indentation
- ✅ Keep functions under ~24 lines
- ✅ Limit loop/if nesting to 2-3 levels
- ✅ One function = one task

### Logic
- ✅ Avoid literals (use constants)
- ✅ Limit boolean expressions to 3-4 conditions
- ✅ Prefer local over global variables
- ✅ Avoid break/continue in loops
- ✅ Don't use exit() or quit()

### Quality
- ✅ Follow DRY principle
- ✅ Handle exceptions gracefully
- ✅ Write comprehensive docstrings
- ✅ Create unit tests
- ✅ Maintain README file
- ✅ Use established libraries

---

## References

- [PEP 8 - Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [NumPy Documentation](https://numpy.org/)
- [Pandas Documentation](https://pandas.pydata.org/)
- [scikit-learn Documentation](https://scikit-learn.org/)

---

*This guide is based on best practices for procedural programming with focus on AI, data science, and machine learning applications. Following these principles will help you create robust, maintainable, and professional Python code.*
