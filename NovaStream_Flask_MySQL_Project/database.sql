
CREATE DATABASE novastream;

USE novastream;

CREATE TABLE history(
    id INT AUTO_INCREMENT PRIMARY KEY,
    movie_name VARCHAR(255),
    viewed_date DATE,
    viewed_time TIME
);
