DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS tours;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS memories;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0
);

CREATE TABLE tours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    date TEXT NOT NULL,
    max_participants INTEGER NOT NULL,
    current_participants INTEGER DEFAULT 0,
    status TEXT DEFAULT 'available'
);

CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tour_id INTEGER NOT NULL,
    user_id INTEGER,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    num_participants INTEGER NOT NULL,
    booking_date TEXT DEFAULT CURRENT_TIMESTAMP,
    payment_status TEXT DEFAULT 'pending', -- 'pending', 'paid', 'failed', 'refunded'
    mpesa_receipt TEXT,                   -- NEW: Stores the M-Pesa transaction ID (e.g., RJ67R923H)
    amount_paid REAL,                     -- NEW: Stores the actual amount paid via M-Pesa
    phone_number_paid TEXT,               -- NEW: Stores the phone number that initiated the payment
    FOREIGN KEY (tour_id) REFERENCES tours (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    image_filename TEXT NOT NULL,
    tour_id INTEGER,
    memory_date TEXT NOT NULL,
    FOREIGN KEY (tour_id) REFERENCES tours (id)
);

-- Insert some sample data
INSERT INTO users (username, email, password, is_admin) VALUES
('admin', 'admin@example.com', 'scrypt:32768:8:1$NyZQ2qyuxKpLJBFN$b8acf4b044d9c04e4dd441b64218cb66711c0e7b25b411ea2cae7a6cfcd8f47ecf199698ce317ccacb8ea7257150e1ade56d7c9ef03461c0e1609a969f3a811b', 1), -- Hashed password for 'admin254d'
('testuser', 'test@example.com', '$2b$12$s0S/U.r3fW1D5lR7r.Q.mOu/dD3oV0XpQ.gV2N.q.w.Q/z.f.x.y', 0); -- Hashed password for 'testpass'


INSERT INTO tours (name, description, price, date, max_participants, status) VALUES
('City Historical Walk', 'Explore the city''s rich history and landmarks.', 25.00, '2025-08-10', 20, 'available'),
('Mountain Hiking Adventure', 'A challenging hike through scenic mountain trails.', 50.00, '2025-08-15', 15, 'available'),
('Coastal Cycling Tour', 'Bike along the beautiful coastline with stunning views.', 35.00, '2025-08-20', 10, 'available'),
('Foodie Tour', 'Discover local culinary delights and hidden gems.', 40.00, '2025-08-25', 12, 'available'),
('Desert Safari (Coming Soon)', 'An exhilarating ride through the dunes.', 75.00, '2025-09-01', 8, 'coming_soon'),
('Old Town Exploration (Done)', 'A nostalgic journey through the ancient streets.', 30.00, '2024-05-10', 25, 'done');

INSERT INTO memories (title, description, image_filename, tour_id, memory_date) VALUES
('Hiking Trail Views', 'Breathtaking vistas from the mountain hike.', 'mountain_hike.jpg', 2, '2024-06-15'),
('Cycling by the Sea', 'Sunny day on the coastal path.', 'coastal_cycling.jpg', 3, '2024-07-20'),
('Delicious Street Food', 'Tasting local delicacies.', 'foodie_tour.jpg', 4, '2024-08-01');