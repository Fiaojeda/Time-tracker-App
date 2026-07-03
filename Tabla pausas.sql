Tabla pausas
CREATE TABLE pausas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada_id INTEGER,
    inicio DATETIME,
    fin DATETIME,
    FOREIGN KEY (jornada_id) REFERENCES jornadas(id)
);