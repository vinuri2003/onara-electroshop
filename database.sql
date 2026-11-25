CREATE DATABASE IF NOT EXISTS electrical_shop_db;
USE electrical_shop_db;

-- 1. Users table (Admin, Owner, Workers, and Customers - Mobile Number is Username)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'owner', 'worker', 'customer') NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(100),
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Electrical Products Catalog (with product photo filename)
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    model_number VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    default_warranty_months INT NOT NULL DEFAULT 12,
    image_filename VARCHAR(255) NULL
);

-- 3. Purchases / Sales (Links Customers, Products, Staff, Payment Method & Warranty)
CREATE TABLE IF NOT EXISTS purchases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    product_id INT NOT NULL,
    sold_by_user_id INT NOT NULL,
    serial_number VARCHAR(100) NOT NULL,
    purchase_price DECIMAL(10, 2) NOT NULL,
    payment_method ENUM('Cash', 'Card', 'Bank Transfer', 'Installment') NOT NULL,
    purchase_date DATE NOT NULL,
    warranty_months INT NOT NULL,
    warranty_expiry DATE NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (sold_by_user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 4. Repairs & Customer Feedback After Repair (with customer repair photo)
CREATE TABLE IF NOT EXISTS repairs_and_feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    purchase_id INT NOT NULL,
    issue_description TEXT NOT NULL,
    repair_status ENUM('Pending', 'In Progress', 'Repaired', 'Delivered') DEFAULT 'Pending',
    repaired_date DATE NULL,
    technician_notes TEXT,
    customer_feedback TEXT,
    rating INT NULL CHECK (rating BETWEEN 1 AND 5),
    repair_photo VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE
);