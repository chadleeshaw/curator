# JavaScript Best Practices Guide
## Writing High-Quality, Maintainable, and Modern JavaScript Code

> This guide provides essential best practices for JavaScript development, covering ES6+ features, modern patterns, and industry standards. Following these guidelines ensures code that is clean, performant, maintainable, and scalable.

---

## Table of Contents
1. [Naming Conventions](#naming-conventions)
2. [Variables and Constants](#variables-and-constants)
3. [Functions](#functions)
4. [Formatting and Style](#formatting-and-style)
5. [Objects and Arrays](#objects-and-arrays)
6. [Async Programming](#async-programming)
7. [Error Handling](#error-handling)
8. [Modules](#modules)
9. [Classes and OOP](#classes-and-oop)
10. [Comparisons and Conditionals](#comparisons-and-conditionals)
11. [Modern ES6+ Features](#modern-es6-features)
12. [Performance](#performance)
13. [Testing](#testing)
14. [Documentation](#documentation)
15. [Security](#security)

---

## Naming Conventions

### General Principles
- **Use descriptive names**: Variables and functions should clearly convey their purpose
- **Be consistent**: Stick to one naming style throughout your codebase
- **Avoid abbreviations**: Write `userName` not `usrNm`

### camelCase for Variables and Functions
```javascript
// Bad
const user_name = 'John';
const UserAge = 25;

// Good
const userName = 'John';
const userAge = 25;

function calculateTotalPrice(items) {
    return items.reduce((sum, item) => sum + item.price, 0);
}
```

### PascalCase for Classes and Constructors
```javascript
// Bad
class userAccount {
    constructor(name) {
        this.name = name;
    }
}

// Good
class UserAccount {
    constructor(name) {
        this.name = name;
    }
}

class DatabaseConnection {
    connect() {
        // Connection logic
    }
}
```

### UPPER_CASE for Constants
```javascript
// Bad
const maxretries = 3;
const apiEndpoint = 'https://api.example.com';

// Good
const MAX_RETRIES = 3;
const API_ENDPOINT = 'https://api.example.com';
const DEFAULT_TIMEOUT = 5000;
```

### Prefix Booleans with is/has/should
```javascript
// Bad
const visible = true;
const authenticated = false;
const loading = true;

// Good
const isVisible = true;
const hasAuthenticated = false;
const shouldLoad = true;
const canEdit = false;
```

### Use Verbs for Functions
```javascript
// Bad
function data() { }
function userData(id) { }

// Good
function getData() { }
function fetchUserData(id) { }
function validateEmail(email) { }
function transformData(data) { }
```

### Private Methods and Properties
Use `#` for truly private fields (ES2022+) or `_` prefix for convention:

```javascript
class BankAccount {
    #balance = 0;  // Private field
    
    constructor(initialBalance) {
        this.#balance = initialBalance;
    }
    
    deposit(amount) {
        this.#validateAmount(amount);
        this.#balance += amount;
    }
    
    #validateAmount(amount) {  // Private method
        if (amount <= 0) {
            throw new Error('Amount must be positive');
        }
    }
}

// Using underscore convention for older code
class LegacyClass {
    constructor() {
        this._privateValue = 42;
    }
    
    _privateMethod() {
        // Convention indicates this is private
    }
}
```

---

## Variables and Constants

### Use const by Default
```javascript
// Bad
var maxUsers = 100;
let apiUrl = 'https://api.example.com';

// Good
const MAX_USERS = 100;
const API_URL = 'https://api.example.com';
```

### Use let for Reassignable Variables
```javascript
// Bad
var counter = 0;
var userName = 'Guest';

// Good
let counter = 0;
let userName = 'Guest';

for (let i = 0; i < 10; i++) {
    // i is block-scoped
}
```

### Never Use var
`var` has function scope and hoisting issues:

```javascript
// Bad - var has function scope
function example() {
    if (true) {
        var x = 10;
    }
    console.log(x); // 10 - accessible outside block!
}

// Good - let has block scope
function example() {
    if (true) {
        let x = 10;
    }
    console.log(x); // ReferenceError: x is not defined
}
```

### Declare Variables at the Top of Their Scope
```javascript
// Bad
function calculateTotal(items) {
    let total = 0;
    for (let i = 0; i < items.length; i++) {
        let tax = 0.1; // Declared inside loop
        total += items[i].price * (1 + tax);
    }
    return total;
}

// Good
function calculateTotal(items) {
    let total = 0;
    const TAX_RATE = 0.1; // Declared at top, const
    
    for (let i = 0; i < items.length; i++) {
        total += items[i].price * (1 + TAX_RATE);
    }
    
    return total;
}
```

### One Variable Per Declaration
```javascript
// Bad
const a = 1, b = 2, c = 3;
let x = 'hello', y = 'world';

// Good
const a = 1;
const b = 2;
const c = 3;

let x = 'hello';
let y = 'world';
```

### Avoid Global Variables
```javascript
// Bad
var globalCounter = 0;

function incrementCounter() {
    globalCounter++;
}

// Good
function createCounter() {
    let counter = 0;
    
    return {
        increment: () => ++counter,
        decrement: () => --counter,
        getValue: () => counter
    };
}

const counter = createCounter();
counter.increment();
```

---

## Functions

### Use Arrow Functions for Callbacks
```javascript
// Bad
const numbers = [1, 2, 3, 4, 5];
const doubled = numbers.map(function(num) {
    return num * 2;
});

// Good
const numbers = [1, 2, 3, 4, 5];
const doubled = numbers.map(num => num * 2);

// Good for multi-line
const processedData = data.map(item => {
    const processed = transform(item);
    return validate(processed);
});
```

### Use Default Parameters
```javascript
// Bad
function createUser(name, role) {
    role = role || 'guest';
    return { name, role };
}

// Good
function createUser(name, role = 'guest') {
    return { name, role };
}

// Good with object destructuring
function configureApp({ port = 3000, host = 'localhost', debug = false } = {}) {
    return { port, host, debug };
}
```

### Keep Functions Small and Focused
```javascript
// Bad - function does too much
function processUserData(userData) {
    // Validate
    if (!userData.email || !userData.name) {
        throw new Error('Invalid data');
    }
    
    // Transform
    const user = {
        email: userData.email.toLowerCase(),
        name: userData.name.trim(),
        createdAt: new Date()
    };
    
    // Save to database
    database.save(user);
    
    // Send email
    emailService.sendWelcome(user.email);
    
    // Log
    logger.info('User created', user);
    
    return user;
}

// Good - single responsibility
function validateUserData(userData) {
    if (!userData.email || !userData.name) {
        throw new Error('Invalid data');
    }
}

function transformUserData(userData) {
    return {
        email: userData.email.toLowerCase(),
        name: userData.name.trim(),
        createdAt: new Date()
    };
}

async function createUser(userData) {
    validateUserData(userData);
    const user = transformUserData(userData);
    await saveUser(user);
    await sendWelcomeEmail(user.email);
    logUserCreation(user);
    return user;
}
```

### Use Named Functions for Better Stack Traces
```javascript
// Bad - anonymous function
const handler = function(event) {
    // Hard to debug in stack traces
};

// Good - named function
const handleClick = function handleClickEvent(event) {
    // Easier to debug
};

// Better - arrow function with clear variable name
const handleFormSubmit = (event) => {
    event.preventDefault();
    // Clear in stack traces
};
```

### Avoid Too Many Parameters
```javascript
// Bad
function createUser(firstName, lastName, email, age, phone, address, city, zip) {
    // Too many parameters
}

// Good - use object parameter
function createUser({ firstName, lastName, email, age, phone, address, city, zip }) {
    return {
        firstName,
        lastName,
        email,
        age,
        phone,
        address,
        city,
        zip
    };
}

// Usage
createUser({
    firstName: 'John',
    lastName: 'Doe',
    email: 'john@example.com',
    age: 30
});
```

### Return Early to Reduce Nesting
```javascript
// Bad
function processPayment(payment) {
    if (payment) {
        if (payment.amount > 0) {
            if (payment.method === 'credit') {
                // Process credit payment
                return true;
            } else {
                return false;
            }
        } else {
            return false;
        }
    } else {
        return false;
    }
}

// Good
function processPayment(payment) {
    if (!payment) return false;
    if (payment.amount <= 0) return false;
    if (payment.method !== 'credit') return false;
    
    // Process credit payment
    return true;
}
```

---

## Formatting and Style

### Use 2 or 4 Spaces for Indentation
```javascript
// Choose one and be consistent
function example() {
    const data = {
        name: 'John',
        age: 30
    };
    
    if (data.age > 18) {
        console.log('Adult');
    }
}
```

### Use Semicolons
```javascript
// Bad
const name = 'John'
const age = 30
const greet = () => console.log('Hello')

// Good
const name = 'John';
const age = 30;
const greet = () => console.log('Hello');
```

### Use Single Quotes for Strings
```javascript
// Bad
const name = "John";
const message = "Hello " + name;

// Good
const name = 'John';
const message = `Hello ${name}`; // Template literals use backticks
```

### Proper Spacing Around Operators
```javascript
// Bad
const sum=a+b;
const isValid=age>18&&hasPermission;

// Good
const sum = a + b;
const isValid = age > 18 && hasPermission;
```

### Line Length Limit (80-120 characters)
```javascript
// Bad - too long
const message = 'This is a very long message that exceeds the recommended line length and should be broken up for better readability';

// Good
const message = 
    'This is a very long message that exceeds the recommended line length ' +
    'and should be broken up for better readability';

// Better with template literals
const message = `
    This is a very long message that exceeds 
    the recommended line length and should be 
    broken up for better readability
`.trim();
```

### Consistent Brace Style
```javascript
// Bad
function example() 
{
    if (condition) 
    {
        doSomething();
    }
}

// Good - K&R style (most common)
function example() {
    if (condition) {
        doSomething();
    }
}
```

### Use Trailing Commas
```javascript
// Good - easier to add/remove items
const user = {
    name: 'John',
    age: 30,
    email: 'john@example.com',
};

const items = [
    'apple',
    'banana',
    'orange',
];
```

---

## Objects and Arrays

### Use Object Literal Syntax
```javascript
// Bad
const obj = new Object();
obj.name = 'John';

// Good
const obj = {
    name: 'John',
    age: 30
};
```

### Use Property Shorthand
```javascript
const name = 'John';
const age = 30;

// Bad
const user = {
    name: name,
    age: age
};

// Good
const user = {
    name,
    age
};
```

### Use Object Destructuring
```javascript
// Bad
function getFullName(user) {
    const firstName = user.firstName;
    const lastName = user.lastName;
    return `${firstName} ${lastName}`;
}

// Good
function getFullName({ firstName, lastName }) {
    return `${firstName} ${lastName}`;
}

// Destructuring with defaults
const { 
    name = 'Guest', 
    role = 'user',
    permissions = []
} = userData;
```

### Use Array Destructuring
```javascript
// Bad
const arr = [1, 2, 3];
const first = arr[0];
const second = arr[1];

// Good
const [first, second, third] = [1, 2, 3];

// Skip elements
const [, , third] = [1, 2, 3];

// Rest operator
const [first, ...rest] = [1, 2, 3, 4, 5];
console.log(rest); // [2, 3, 4, 5]
```

### Use Spread Operator
```javascript
// Copying arrays
const original = [1, 2, 3];
const copy = [...original];

// Combining arrays
const arr1 = [1, 2, 3];
const arr2 = [4, 5, 6];
const combined = [...arr1, ...arr2];

// Copying objects
const user = { name: 'John', age: 30 };
const updatedUser = { ...user, age: 31 };

// Function arguments
const numbers = [1, 2, 3];
Math.max(...numbers); // 3
```

### Use Array Methods Over Loops
```javascript
// Bad
const numbers = [1, 2, 3, 4, 5];
const doubled = [];
for (let i = 0; i < numbers.length; i++) {
    doubled.push(numbers[i] * 2);
}

// Good
const doubled = numbers.map(n => n * 2);

// Filter
const evens = numbers.filter(n => n % 2 === 0);

// Reduce
const sum = numbers.reduce((total, n) => total + n, 0);

// Find
const found = numbers.find(n => n > 3);

// Some/Every
const hasEven = numbers.some(n => n % 2 === 0);
const allPositive = numbers.every(n => n > 0);
```

### Avoid Array Constructor
```javascript
// Bad
const arr = new Array(1, 2, 3);

// Good
const arr = [1, 2, 3];

// For empty array with length
const arr = Array(5).fill(0);
// or
const arr = [...Array(5)].map(() => 0);
```

---

## Async Programming

### Use async/await Over Promises
```javascript
// Bad - promise chains
function fetchUserData(userId) {
    return fetch(`/api/users/${userId}`)
        .then(response => response.json())
        .then(user => {
            return fetch(`/api/posts/${user.id}`)
                .then(response => response.json())
                .then(posts => {
                    return { user, posts };
                });
        })
        .catch(error => {
            console.error(error);
        });
}

// Good - async/await
async function fetchUserData(userId) {
    try {
        const response = await fetch(`/api/users/${userId}`);
        const user = await response.json();
        
        const postsResponse = await fetch(`/api/posts/${user.id}`);
        const posts = await postsResponse.json();
        
        return { user, posts };
    } catch (error) {
        console.error(error);
        throw error;
    }
}
```

### Handle Errors in Async Functions
```javascript
// Bad - unhandled rejection
async function fetchData() {
    const response = await fetch('/api/data');
    return response.json();
}

// Good
async function fetchData() {
    try {
        const response = await fetch('/api/data');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('Failed to fetch data:', error);
        throw error;
    }
}
```

### Use Promise.all for Parallel Operations
```javascript
// Bad - sequential
async function fetchAllData() {
    const users = await fetch('/api/users').then(r => r.json());
    const posts = await fetch('/api/posts').then(r => r.json());
    const comments = await fetch('/api/comments').then(r => r.json());
    return { users, posts, comments };
}

// Good - parallel
async function fetchAllData() {
    const [users, posts, comments] = await Promise.all([
        fetch('/api/users').then(r => r.json()),
        fetch('/api/posts').then(r => r.json()),
        fetch('/api/comments').then(r => r.json())
    ]);
    return { users, posts, comments };
}

// Handle partial failures with Promise.allSettled
async function fetchDataWithFailures() {
    const results = await Promise.allSettled([
        fetch('/api/users').then(r => r.json()),
        fetch('/api/posts').then(r => r.json()),
        fetch('/api/comments').then(r => r.json())
    ]);
    
    return results.filter(r => r.status === 'fulfilled')
                  .map(r => r.value);
}
```

### Avoid Async in Loops
```javascript
// Bad - sequential execution
async function processItems(items) {
    for (const item of items) {
        await processItem(item); // Waits for each one
    }
}

// Good - parallel execution
async function processItems(items) {
    await Promise.all(items.map(item => processItem(item)));
}

// If order matters or you need rate limiting
async function processItemsSequentially(items) {
    const results = [];
    for (const item of items) {
        results.push(await processItem(item));
    }
    return results;
}
```

---

## Error Handling

### Use Descriptive Error Messages
```javascript
// Bad
throw new Error('Error');
throw new Error('Something went wrong');

// Good
throw new Error('User validation failed: email is required');
throw new Error(`Failed to fetch user with ID ${userId}: ${error.message}`);
```

### Create Custom Error Classes
```javascript
class ValidationError extends Error {
    constructor(message, field) {
        super(message);
        this.name = 'ValidationError';
        this.field = field;
        this.timestamp = new Date();
    }
}

class NetworkError extends Error {
    constructor(message, statusCode) {
        super(message);
        this.name = 'NetworkError';
        this.statusCode = statusCode;
    }
}

// Usage
function validateEmail(email) {
    if (!email.includes('@')) {
        throw new ValidationError('Invalid email format', 'email');
    }
}

try {
    validateEmail('invalid');
} catch (error) {
    if (error instanceof ValidationError) {
        console.error(`Validation error in ${error.field}: ${error.message}`);
    }
}
```

### Always Handle Promise Rejections
```javascript
// Bad
fetch('/api/data')
    .then(response => response.json())
    .then(data => console.log(data));

// Good
fetch('/api/data')
    .then(response => response.json())
    .then(data => console.log(data))
    .catch(error => console.error('Fetch failed:', error));

// Better with async/await
async function fetchData() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        console.log(data);
    } catch (error) {
        console.error('Fetch failed:', error);
    }
}
```

### Use try/catch Appropriately
```javascript
// Bad - too broad
try {
    const user = await fetchUser();
    const posts = await fetchPosts();
    const comments = await fetchComments();
    const result = processData(user, posts, comments);
    displayResult(result);
} catch (error) {
    console.error(error); // Which operation failed?
}

// Good - specific error handling
async function loadUserData() {
    let user, posts, comments;
    
    try {
        user = await fetchUser();
    } catch (error) {
        console.error('Failed to fetch user:', error);
        throw new Error('User data unavailable');
    }
    
    try {
        [posts, comments] = await Promise.all([
            fetchPosts(),
            fetchComments()
        ]);
    } catch (error) {
        console.error('Failed to fetch user content:', error);
        // Continue with empty arrays
        posts = [];
        comments = [];
    }
    
    return processData(user, posts, comments);
}
```

---

## Modules

### Use ES6 Modules
```javascript
// Bad - CommonJS
const express = require('express');
const helper = require('./helper');

// Good - ES6 modules
import express from 'express';
import { helperFunction } from './helper.js';
```

### Named Exports vs Default Exports
```javascript
// helper.js - Named exports (preferred for utilities)
export function formatDate(date) {
    return date.toISOString();
}

export function validateEmail(email) {
    return email.includes('@');
}

// user.js - Default export (for main class/component)
export default class User {
    constructor(name) {
        this.name = name;
    }
}

// Usage
import User from './user.js';
import { formatDate, validateEmail } from './helper.js';
```

### Import Order
```javascript
// 1. External dependencies
import React from 'react';
import express from 'express';

// 2. Internal modules
import { database } from './database.js';
import { config } from './config.js';

// 3. Local imports
import './styles.css';
```

### Avoid Wildcard Imports
```javascript
// Bad
import * as utils from './utils.js';

// Good
import { formatDate, formatCurrency, validateEmail } from './utils.js';
```

---

## Classes and OOP

### Use Class Syntax
```javascript
// Bad - constructor function
function User(name, email) {
    this.name = name;
    this.email = email;
}

User.prototype.greet = function() {
    return `Hello, ${this.name}`;
};

// Good - class syntax
class User {
    constructor(name, email) {
        this.name = name;
        this.email = email;
    }
    
    greet() {
        return `Hello, ${this.name}`;
    }
}
```

### Use Private Fields
```javascript
class BankAccount {
    #balance = 0; // Private field
    
    constructor(initialBalance) {
        this.#balance = initialBalance;
    }
    
    deposit(amount) {
        if (amount <= 0) {
            throw new Error('Amount must be positive');
        }
        this.#balance += amount;
        return this.#balance;
    }
    
    getBalance() {
        return this.#balance;
    }
}

const account = new BankAccount(1000);
// account.#balance; // SyntaxError: Private field
```

### Use Getters and Setters
```javascript
class Temperature {
    constructor(celsius) {
        this._celsius = celsius;
    }
    
    get fahrenheit() {
        return this._celsius * 9/5 + 32;
    }
    
    set fahrenheit(value) {
        this._celsius = (value - 32) * 5/9;
    }
    
    get celsius() {
        return this._celsius;
    }
    
    set celsius(value) {
        this._celsius = value;
    }
}

const temp = new Temperature(25);
console.log(temp.fahrenheit); // 77
temp.fahrenheit = 86;
console.log(temp.celsius); // 30
```

### Use Static Methods
```javascript
class MathHelper {
    static add(a, b) {
        return a + b;
    }
    
    static multiply(a, b) {
        return a * b;
    }
    
    static calculateAverage(numbers) {
        return numbers.reduce((sum, n) => sum + n, 0) / numbers.length;
    }
}

// Usage - no instantiation needed
const sum = MathHelper.add(5, 3);
const avg = MathHelper.calculateAverage([1, 2, 3, 4, 5]);
```

---

## Comparisons and Conditionals

### Use Strict Equality
```javascript
// Bad
if (value == 5) { }
if (user != null) { }

// Good
if (value === 5) { }
if (user !== null) { }
```

### Use Ternary for Simple Conditions
```javascript
// Bad
let status;
if (isActive) {
    status = 'active';
} else {
    status = 'inactive';
}

// Good
const status = isActive ? 'active' : 'inactive';

// Bad - nested ternary
const value = a ? b : c ? d : e;

// Good - use if/else for complex logic
let value;
if (a) {
    value = b;
} else if (c) {
    value = d;
} else {
    value = e;
}
```

### Use Optional Chaining
```javascript
// Bad
const street = user && user.address && user.address.street;

// Good
const street = user?.address?.street;

// With function calls
const result = obj.method?.();

// With arrays
const firstItem = arr?.[0];
```

### Use Nullish Coalescing
```javascript
// Bad - wrong for 0, '', false
const value = input || 'default';

// Good
const value = input ?? 'default';

// Examples
const count = 0;
const displayCount = count ?? 'N/A'; // 0 (not 'N/A')

const name = '';
const displayName = name ?? 'Anonymous'; // '' (not 'Anonymous')

// Use || for falsy values
const displayName2 = name || 'Anonymous'; // 'Anonymous'
```

### Avoid Truthy/Falsy Confusion
```javascript
// Be explicit when needed
const array = [];

// Bad - array is truthy
if (array) {
    console.log('Has items'); // This runs!
}

// Good
if (array.length > 0) {
    console.log('Has items');
}

// Checking for undefined/null
if (value !== undefined && value !== null) { }

// Or use nullish coalescing
const result = value ?? defaultValue;
```

---

## Modern ES6+ Features

### Template Literals
```javascript
// Bad
const message = 'Hello ' + name + ', you have ' + count + ' messages.';

// Good
const message = `Hello ${name}, you have ${count} messages.`;

// Multi-line
const html = `
    <div class="card">
        <h2>${title}</h2>
        <p>${description}</p>
    </div>
`;
```

### Rest Parameters
```javascript
// Bad
function sum() {
    const args = Array.prototype.slice.call(arguments);
    return args.reduce((total, n) => total + n, 0);
}

// Good
function sum(...numbers) {
    return numbers.reduce((total, n) => total + n, 0);
}

sum(1, 2, 3, 4); // 10
```

### Optional Chaining and Nullish Coalescing
```javascript
// Complex object access
const user = {
    name: 'John',
    address: {
        city: 'New York'
    }
};

// Old way
const zipCode = user && user.address && user.address.zipCode;

// New way
const zipCode = user?.address?.zipCode ?? 'N/A';
```

### for...of Loops
```javascript
// Bad
const items = [1, 2, 3, 4, 5];
for (let i = 0; i < items.length; i++) {
    console.log(items[i]);
}

// Good
for (const item of items) {
    console.log(item);
}

// With index
for (const [index, item] of items.entries()) {
    console.log(index, item);
}

// For objects
const obj = { a: 1, b: 2, c: 3 };
for (const [key, value] of Object.entries(obj)) {
    console.log(key, value);
}
```

### Map and Set
```javascript
// Use Map for key-value pairs
const userMap = new Map();
userMap.set('user1', { name: 'John', age: 30 });
userMap.set('user2', { name: 'Jane', age: 25 });

// Use Set for unique values
const uniqueNumbers = new Set([1, 2, 3, 3, 4, 4, 5]);
console.log([...uniqueNumbers]); // [1, 2, 3, 4, 5]

// Set operations
const set = new Set();
set.add(1);
set.add(2);
set.has(1); // true
set.delete(1);
set.size; // 1
```

---

## Performance

### Debounce and Throttle
```javascript
// Debounce - execute after user stops typing
function debounce(func, delay) {
    let timeoutId;
    return function(...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
}

// Usage
const searchInput = document.getElementById('search');
const debouncedSearch = debounce(performSearch, 300);
searchInput.addEventListener('input', debouncedSearch);

// Throttle - execute at most once per interval
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}
```

### Avoid Premature Optimization
```javascript
// Don't optimize until you measure
// Use performance tools to identify bottlenecks

// Bad - over-optimized for no reason
const result = array.reduce((acc, item) => {
    const temp = item * 2;
    return acc + temp;
}, 0);

// Good - readable
const result = array.reduce((acc, item) => acc + item * 2, 0);
```

### Use Web Workers for Heavy Computation
```javascript
// main.js
const worker = new Worker('worker.js');

worker.postMessage({ numbers: [1, 2, 3, 4, 5] });

worker.onmessage = (event) => {
    console.log('Result:', event.data);
};

// worker.js
self.onmessage = (event) => {
    const { numbers } = event.data;
    const sum = numbers.reduce((a, b) => a + b, 0);
    self.postMessage(sum);
};
```

### Memoization for Expensive Functions
```javascript
function memoize(fn) {
    const cache = new Map();
    return function(...args) {
        const key = JSON.stringify(args);
        if (cache.has(key)) {
            return cache.get(key);
        }
        const result = fn.apply(this, args);
        cache.set(key, result);
        return result;
    };
}

// Usage
const expensiveFunction = (n) => {
    console.log('Computing...');
    return n * 2;
};

const memoized = memoize(expensiveFunction);
memoized(5); // Computing... 10
memoized(5); // 10 (from cache)
```

---

## Testing

### Write Unit Tests
```javascript
// user.test.js (Jest example)
import { validateEmail, formatUsername } from './user.js';

describe('User utilities', () => {
    describe('validateEmail', () => {
        test('returns true for valid email', () => {
            expect(validateEmail('test@example.com')).toBe(true);
        });
        
        test('returns false for invalid email', () => {
            expect(validateEmail('invalid')).toBe(false);
            expect(validateEmail('')).toBe(false);
            expect(validateEmail(null)).toBe(false);
        });
    });
    
    describe('formatUsername', () => {
        test('trims and lowercases username', () => {
            expect(formatUsername('  JohnDoe  ')).toBe('johndoe');
        });
        
        test('handles empty string', () => {
            expect(formatUsername('')).toBe('');
        });
    });
});
```

### Test Async Code
```javascript
// async.test.js
describe('Async operations', () => {
    test('fetches user data', async () => {
        const user = await fetchUser(1);
        expect(user.id).toBe(1);
        expect(user.name).toBeDefined();
    });
    
    test('handles fetch errors', async () => {
        await expect(fetchUser(-1)).rejects.toThrow('User not found');
    });
});
```

### Use Test Coverage
```javascript
// package.json
{
    "scripts": {
        "test": "jest",
        "test:coverage": "jest --coverage"
    }
}
```

### Follow AAA Pattern
```javascript
test('calculates total price with tax', () => {
    // Arrange
    const items = [
        { price: 10, quantity: 2 },
        { price: 5, quantity: 3 }
    ];
    const taxRate = 0.1;
    
    // Act
    const total = calculateTotalWithTax(items, taxRate);
    
    // Assert
    expect(total).toBe(38.5); // (20 + 15) * 1.1
});
```

---

## Documentation

### Use JSDoc Comments
```javascript
/**
 * Calculates the total price including tax
 * @param {Array<{price: number, quantity: number}>} items - Array of items
 * @param {number} taxRate - Tax rate as decimal (e.g., 0.1 for 10%)
 * @returns {number} Total price including tax
 * @throws {Error} If items array is empty
 * @example
 * const items = [{ price: 10, quantity: 2 }];
 * const total = calculateTotal(items, 0.1);
 * // returns 22
 */
function calculateTotal(items, taxRate) {
    if (items.length === 0) {
        throw new Error('Items array cannot be empty');
    }
    
    const subtotal = items.reduce((sum, item) => {
        return sum + (item.price * item.quantity);
    }, 0);
    
    return subtotal * (1 + taxRate);
}
```

### Document Complex Logic
```javascript
function processData(data) {
    // Remove duplicates based on ID
    const uniqueData = [...new Map(
        data.map(item => [item.id, item])
    ).values()];
    
    // Sort by priority (higher first) then by date (newer first)
    return uniqueData.sort((a, b) => {
        if (a.priority !== b.priority) {
            return b.priority - a.priority;
        }
        return new Date(b.date) - new Date(a.date);
    });
}
```

### README for Projects
```markdown
# Project Name

## Description
Brief description of what the project does.

## Installation
```bash
npm install
```

## Usage
```javascript
import { myFunction } from 'my-library';
myFunction();
```

## API Reference
### myFunction(param1, param2)
Description of the function.

**Parameters:**
- `param1` (string): Description
- `param2` (number): Description

**Returns:** Description

## Testing
```bash
npm test
```

## Contributing
Guidelines for contributing.

## License
MIT
```

---

## Security

### Avoid eval()
```javascript
// Bad
const userInput = '1 + 1';
eval(userInput); // Dangerous!

// Good
const result = Function('return ' + sanitizedInput)();
// Or better, use a math parser library
```

### Sanitize User Input
```javascript
function sanitizeInput(input) {
    return input
        .replace(/[<>]/g, '') // Remove HTML tags
        .trim();
}

// Use libraries for HTML escaping
import DOMPurify from 'dompurify';
const clean = DOMPurify.sanitize(dirty);
```

### Use Content Security Policy
```javascript
// Set CSP headers
app.use((req, res, next) => {
    res.setHeader(
        'Content-Security-Policy',
        "default-src 'self'; script-src 'self' 'unsafe-inline'"
    );
    next();
});
```

### Store Sensitive Data Securely
```javascript
// Bad
const apiKey = 'sk-1234567890';

// Good - use environment variables
const apiKey = process.env.API_KEY;

// Use .env file
// API_KEY=sk-1234567890

// Load with dotenv
import 'dotenv/config';
```

---

## Summary Checklist

### Naming & Style
- ✅ Use camelCase for variables and functions
- ✅ Use PascalCase for classes
- ✅ Use UPPER_CASE for constants
- ✅ Use descriptive names
- ✅ Use semicolons consistently
- ✅ Use 2 or 4 spaces for indentation

### Variables
- ✅ Use `const` by default
- ✅ Use `let` for reassignable variables
- ✅ Never use `var`
- ✅ Avoid global variables

### Functions
- ✅ Keep functions small and focused
- ✅ Use arrow functions for callbacks
- ✅ Use default parameters
- ✅ Return early to reduce nesting
- ✅ Max 3-4 parameters (use object for more)

### Modern JavaScript
- ✅ Use template literals
- ✅ Use destructuring
- ✅ Use spread operator
- ✅ Use async/await over promises
- ✅ Use optional chaining (?.)
- ✅ Use nullish coalescing (??)

### Code Quality
- ✅ Handle errors properly
- ✅ Write unit tests
- ✅ Document complex logic
- ✅ Use ESLint and Prettier
- ✅ Review code before committing

---

## Tools & Resources

### Linting and Formatting
- **ESLint**: JavaScript linting
- **Prettier**: Code formatting
- **Husky**: Git hooks for automated checks

### Testing
- **Jest**: Testing framework
- **Mocha/Chai**: Alternative testing tools
- **Cypress**: End-to-end testing

### Documentation
- **JSDoc**: API documentation
- **TypeScript**: Type safety

### References
- [MDN Web Docs](https://developer.mozilla.org/)
- [JavaScript.info](https://javascript.info/)
- [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript)
- [You Don't Know JS](https://github.com/getify/You-Dont-Know-JS)

---

*This guide follows industry best practices and modern JavaScript standards (ES6+). Use these principles to write clean, maintainable, and performant JavaScript code.*
