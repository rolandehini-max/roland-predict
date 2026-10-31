# ============================================================
# CIVI-PREDICT — NOUVELLE VERSION
# PARTIE 1/2
# Base de données, calculs et fonctions
# NE PAS EXÉCUTER AVANT D'AVOIR AJOUTÉ LA PARTIE 2/2.
# ============================================================

import streamlit as st
import sqlite3
import random
import io
import math
import json

from datetime import date, datetime, timedelta
from statistics import mean, median, NormalDist


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="CIVI-PREDICT",
    page_icon="🏗️",
    layout="wide"
)

DB_NAME = "civi_predict.db"


# ============================================================
# CONNEXION À LA BASE DE DONNÉES
# ============================================================

def connecter_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def colonnes_table(conn, table):
    resultat = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    return {ligne["name"] for ligne in resultat}


def ajouter_colonne_si_absente(
    conn, table, colonne, definition
):
    colonnes = colonnes_table(conn, table)

    if colonne not in colonnes:
        conn.execute(
            f"ALTER TABLE {table} "
            f"ADD COLUMN {colonne} {definition}"
        )


def initialiser_db():
    conn = connecter_db()

    # --------------------------------------------------------
    # CHANTIERS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chantiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            lieu TEXT,
            responsable TEXT,
            duree REAL DEFAULT 0,
            budget REAL DEFAULT 0,
            date_demarrage TEXT
        )
    """)

    for colonne, definition in {
        "nom": "TEXT",
        "lieu": "TEXT",
        "responsable": "TEXT",
        "duree": "REAL DEFAULT 0",
        "budget": "REAL DEFAULT 0",
        "date_demarrage": "TEXT"
    }.items():
        ajouter_colonne_si_absente(
            conn, "chantiers", colonne, definition
        )

    # --------------------------------------------------------
    # DÉPENSES
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS depenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chantier_id INTEGER,
            categorie TEXT,
            montant REAL DEFAULT 0,
            description TEXT,
            date_depense TEXT,
            FOREIGN KEY (chantier_id)
                REFERENCES chantiers(id)
        )
    """)

    for colonne, definition in {
        "chantier_id": "INTEGER",
        "categorie": "TEXT",
        "montant": "REAL DEFAULT 0",
        "description": "TEXT",
        "date_depense": "TEXT"
    }.items():
        ajouter_colonne_si_absente(
            conn, "depenses", colonne, definition
        )

    # --------------------------------------------------------
    # AVANCEMENTS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS avancements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chantier_id INTEGER,
            pourcentage REAL DEFAULT 0,
            description TEXT,
            date_avancement TEXT,
            FOREIGN KEY (chantier_id)
                REFERENCES chantiers(id)
        )
    """)

    for colonne, definition in {
        "chantier_id": "INTEGER",
        "pourcentage": "REAL DEFAULT 0",
        "description": "TEXT",
        "date_avancement": "TEXT"
    }.items():
        ajouter_colonne_si_absente(
            conn, "avancements", colonne, definition
        )

    # Migration des anciennes colonnes d'avancement,
    # si elles existent dans une ancienne version.
    colonnes_av = colonnes_table(conn, "avancements")

    if "avancement_reel" in colonnes_av:
        conn.execute("""
            UPDATE avancements
            SET pourcentage = avancement_reel
            WHERE (pourcentage IS NULL OR pourcentage = 0)
        """)

    if "date_suivi" in colonnes_av:
        conn.execute("""
            UPDATE avancements
            SET date_avancement = date_suivi
            WHERE date_avancement IS NULL
               OR date_avancement = ''
        """)

    # --------------------------------------------------------
    # ACTIVITÉS DE CONSTRUCTION
    # NOUVELLE TABLE POUR LE DIAGRAMME DE GANTT
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS activites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chantier_id INTEGER NOT NULL,
            nom TEXT NOT NULL,
            description TEXT,
            date_debut_prevue TEXT NOT NULL,
            duree_prevue REAL DEFAULT 1,
            date_debut_reelle TEXT,
            duree_reelle REAL,
            avancement REAL DEFAULT 0,
            statut TEXT DEFAULT 'À faire',
            dependance_id INTEGER,
            cout_prevu REAL DEFAULT 0,
            observations TEXT,
            FOREIGN KEY (chantier_id)
                REFERENCES chantiers(id),
            FOREIGN KEY (dependance_id)
                REFERENCES activites(id)
        )
    """)

    # --------------------------------------------------------
    # RISQUES
    # On conserve les colonnes déjà présentes.
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS risques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chantier_id INTEGER,
            nom TEXT,
            probabilite REAL DEFAULT 1,
            impact REAL DEFAULT 1,
            mesure_prevention TEXT,
            statut TEXT DEFAULT 'À surveiller',
            date_enregistrement TEXT,
            FOREIGN KEY (chantier_id)
                REFERENCES chantiers(id)
        )
    """)

    for colonne, definition in {
        "chantier_id": "INTEGER",
        "nom": "TEXT",
        "probabilite": "REAL DEFAULT 1",
        "impact": "REAL DEFAULT 1",
        "mesure_prevention": "TEXT",
        "statut": "TEXT DEFAULT 'À surveiller'",
        "date_enregistrement": "TEXT",
        "activite_id": "INTEGER"
    }.items():
        ajouter_colonne_si_absente(
            conn, "risques", colonne, definition
        )

    # --------------------------------------------------------
    # INCIDENTS
    # --------------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chantier_id INTEGER,
            titre TEXT,
            description TEXT,
            gravite TEXT,
            cout_estime REAL DEFAULT 0,
            jours_retard REAL DEFAULT 0,
            date_incident TEXT,
            statut TEXT DEFAULT 'Ouvert',
            FOREIGN KEY (chantier_id)
                REFERENCES chantiers(id)
        )
    """)

    for colonne, definition in {
        "chantier_id": "INTEGER",
        "titre": "TEXT",
        "description": "TEXT",
        "gravite": "TEXT",
        "cout_estime": "REAL DEFAULT 0",
        "jours_retard": "REAL DEFAULT 0",
        "date_incident": "TEXT",
        "statut": "TEXT DEFAULT 'Ouvert'"
    }.items():
        ajouter_colonne_si_absente(
            conn, "incidents", colonne, definition
        )

    conn.commit()
    conn.close()


initialiser_db()


# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def fcfa(valeur):
    valeur = float(valeur or 0)

    return (
        f"{valeur:,.0f} FCFA"
        .replace(",", " ")
    )


def nombre(valeur, decimales=2):
    valeur = float(valeur or 0)

    return (
        f"{valeur:,.{decimales}f}"
        .replace(",", " ")
    )


def lire_chantiers():
    conn = connecter_db()

    resultat = conn.execute("""
        SELECT *
        FROM chantiers
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return [dict(ligne) for ligne in resultat]


def obtenir_chantier(chantier_id):
    conn = connecter_db()

    resultat = conn.execute("""
        SELECT *
        FROM chantiers
        WHERE id = ?
    """, (chantier_id,)).fetchone()

    conn.close()

    return dict(resultat) if resultat else None


def ajouter_chantier_db(
    nom, lieu, responsable,
    duree, budget, date_demarrage
):
    conn = connecter_db()

    conn.execute("""
        INSERT INTO chantiers
        (nom, lieu, responsable, duree, budget, date_demarrage)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        nom, lieu, responsable,
        duree, budget, str(date_demarrage)
    ))

    conn.commit()
    conn.close()


def modifier_chantier_db(
    chantier_id, nom, lieu, responsable,
    duree, budget, date_demarrage
):
    conn = connecter_db()

    conn.execute("""
        UPDATE chantiers
        SET nom = ?,
            lieu = ?,
            responsable = ?,
            duree = ?,
            budget = ?,
            date_demarrage = ?
        WHERE id = ?
    """, (
        nom, lieu, responsable,
        duree, budget, str(date_demarrage),
        chantier_id
    ))

    conn.commit()
    conn.close()


def supprimer_chantier_db(chantier_id):
    conn = connecter_db()

    # Suppression des données liées au chantier.
    # Cette fonction n'est appelée que si l'utilisateur
    # confirme la suppression dans l'interface.
    conn.execute(
        "DELETE FROM depenses WHERE chantier_id = ?",
        (chantier_id,)
    )

    conn.execute(
        "DELETE FROM avancements WHERE chantier_id = ?",
        (chantier_id,)
    )

    conn.execute(
        "DELETE FROM risques WHERE chantier_id = ?",
        (chantier_id,)
    )

    conn.execute(
        "DELETE FROM incidents WHERE chantier_id = ?",
        (chantier_id,)
    )

    conn.execute(
        "DELETE FROM activites WHERE chantier_id = ?",
        (chantier_id,)
    )

    conn.execute(
        "DELETE FROM chantiers WHERE id = ?",
        (chantier_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# GESTION DES DÉPENSES
# ============================================================

def lire_depenses(chantier_id=None):
    conn = connecter_db()

    if chantier_id is None:
        resultat = conn.execute("""
            SELECT d.*, c.nom AS nom_chantier
            FROM depenses d
            LEFT JOIN chantiers c
                ON c.id = d.chantier_id
            ORDER BY d.id DESC
        """).fetchall()
    else:
        resultat = conn.execute("""
            SELECT *
            FROM depenses
            WHERE chantier_id = ?
            ORDER BY id DESC
        """, (chantier_id,)).fetchall()

    conn.close()

    return [dict(ligne) for ligne in resultat]


def ajouter_depense_db(
    chantier_id, categorie, montant,
    description, date_depense
):
    conn = connecter_db()

    conn.execute("""
        INSERT INTO depenses
        (chantier_id, categorie, montant,
         description, date_depense)
        VALUES (?, ?, ?, ?, ?)
    """, (
        chantier_id, categorie, montant,
        description, str(date_depense)
    ))

    conn.commit()
    conn.close()


def supprimer_depense_db(depense_id):
    conn = connecter_db()

    conn.execute(
        "DELETE FROM depenses WHERE id = ?",
        (depense_id,)
    )

    conn.commit()
    conn.close()


def total_depenses(chantier_id):
    conn = connecter_db()

    resultat = conn.execute("""
        SELECT COALESCE(SUM(montant), 0) AS total
        FROM depenses
        WHERE chantier_id = ?
    """, (chantier_id,)).fetchone()

    conn.close()

    return float(resultat["total"] or 0)


# ============================================================
# SUIVI DE L'AVANCEMENT
# ============================================================

def lire_avancements(chantier_id):
    conn = connecter_db()

    resultat = conn.execute("""
        SELECT *
        FROM avancements
        WHERE chantier_id = ?
        ORDER BY date_avancement ASC, id ASC
    """, (chantier_id,)).fetchall()

    conn.close()

    return [dict(ligne) for ligne in resultat]


def dernier_avancement(chantier_id):
    conn = connecter_db()

    resultat = conn.execute("""
        SELECT pourcentage
        FROM avancements
        WHERE chantier_id = ?
        ORDER BY date_avancement DESC, id DESC
        LIMIT 1
    """, (chantier_id,)).fetchone()

    conn.close()

    if resultat:
        return float(resultat["pourcentage"] or 0)

    return 0.0


def ajouter_avancement_db(
    chantier_id, pourcentage,
    description, date_avancement
):
    conn = connecter_db()

    conn.execute("""
        INSERT INTO avancements
        (chantier_id, pourcentage,
         description, date_avancement)
        VALUES (?, ?, ?, ?)
    """, (
        chantier_id, pourcentage,
        description, str(date_avancement)
    ))

    conn.commit()
    conn.close()


# ============================================================
# GESTION DES ACTIVITÉS DE CONSTRUCTION
# ============================================================

def lire_activites(chantier_id):
    conn = connecter_db()

    resultat = conn.execute("""
        SELECT a.*,
               d.nom AS nom_dependance
        FROM activites a
        LEFT JOIN activites d
            ON d.id = a.dependance_id
        WHERE a.chantier_id = ?
        ORDER BY a.date_debut_prevue, a.id
    """, (chantier_id,)).fetchall()

    conn.close()

    return [dict(ligne) for ligne in resultat]


def ajouter_activite_db(
    chantier_id,
    nom,
    description,
    date_debut_prevue,
    duree_prevue,
    date_debut_reelle,
    duree_reelle,
    avancement,
    statut,
    dependance_id,
    cout_prevu,
    observations
):
    conn = connecter_db()

    conn.execute("""
        INSERT INTO activites (
            chantier_id, nom, description,
            date_debut_prevue, duree_prevue,
            date_debut_reelle, duree_reelle,
            avancement, statut, dependance_id,
            cout_prevu, observations
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chantier_id,
        nom,
        description,
        str(date_debut_prevue),
        duree_prevue,
        str(date_debut_reelle) if date_debut_reelle else None,
        duree_reelle,
        avancement,
        statut,
        dependance_id,
        cout_prevu,
        observations
    ))

    conn.commit()
    conn.close()


def modifier_activite_db(
    activite_id,
    nom,
    description,
    date_debut_prevue,
    duree_prevue,
    date_debut_reelle,
    duree_reelle,
    avancement,
    statut,
    dependance_id,
    cout_prevu,
    observations
):
    conn = connecter_db()

    conn.execute("""
        UPDATE activites
        SET nom = ?,
            description = ?,
            date_debut_prevue = ?,
            duree_prevue = ?,
            date_debut_reelle = ?,
            duree_reelle = ?,
            avancement = ?,
            statut = ?,
            dependance_id = ?,
            cout_prevu = ?,
            observations = ?
        WHERE id = ?
    """, (
        nom,
        description,
        str(date_debut_prevue),
        duree_prevue,
        str(date_debut_reelle) if date_debut_reelle else None,
        duree_reelle,
        avancement,
        statut,
        dependance_id,
        cout_prevu,
        observations,
        activite_id
    ))

    conn.commit()
    conn.close()


def supprimer_activite_db(activite_id):
    conn = connecter_db()

    # Les activités qui dépendent de celle-ci perdent
    # leur dépendance, mais ne sont pas supprimées.
    conn.execute("""
        UPDATE activites
        SET dependance_id = NULL
        WHERE dependance_id = ?
    """, (activite_id,))

    conn.execute("""
        UPDATE risques
        SET activite_id = NULL
        WHERE activite_id = ?
    """, (activite_id,))

    conn.execute(
        "DELETE FROM activites WHERE id = ?",
        (activite_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# GESTION DES RISQUES
# ============================================================

def lire_risques(chantier_id=None):
    conn = connecter_db()

    if chantier_id is None:
        resultat = conn.execute("""
            SELECT r.*,
                   c.nom AS nom_chantier,
                   a.nom AS nom_activite
            FROM risques r
            LEFT JOIN chantiers c
                ON c.id = r.chantier_id
            LEFT JOIN activites a
                ON a.id = r.activite_id
            ORDER BY r.id DESC
        """).fetchall()
    else:
        resultat = conn.execute("""
            SELECT r.*,
                   a.nom AS nom_activite
            FROM risques r
            LEFT JOIN activites a
                ON a.id = r.activite_id
            WHERE r.chantier_id = ?
            ORDER BY r.id DESC
        """, (chantier_id,)).fetchall()

    conn.close()

    return [dict(ligne) for ligne in resultat]


def ajouter_risque_db(
    chantier_id,
    nom,
    probabilite,
    impact,
    mesure_prevention,
    statut,
    activite_id=None
):
    conn = connecter_db()

    conn.execute("""
        INSERT INTO risques (
            chantier_id, nom, probabilite,
            impact, mesure_prevention,
            statut, date_enregistrement, activite_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chantier_id,
        nom,
        probabilite,
        impact,
        mesure_prevention,
        statut,
        date.today().isoformat(),
        activite_id
    ))

    conn.commit()
    conn.close()


def supprimer_risque_db(risque_id):
    conn = connecter_db()

    conn.execute(
        "DELETE FROM risques WHERE id = ?",
        (risque_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# GESTION DES INCIDENTS
# ============================================================

def lire_incidents(chantier_id=None):
    conn = connecter_db()

    if chantier_id is None:
        resultat = conn.execute("""
            SELECT i.*, c.nom AS nom_chantier
            FROM incidents i
            LEFT JOIN chantiers c
                ON c.id = i.chantier_id
            ORDER BY i.id DESC
        """).fetchall()
    else:
        resultat = conn.execute("""
            SELECT *
            FROM incidents
            WHERE chantier_id = ?
            ORDER BY id DESC
        """, (chantier_id,)).fetchall()

    conn.close()

    return [dict(ligne) for ligne in resultat]


def ajouter_incident_db(
    chantier_id,
    titre,
    description,
    gravite,
    cout_estime,
    jours_retard,
    statut
):
    conn = connecter_db()

    conn.execute("""
        INSERT INTO incidents (
            chantier_id, titre, description,
            gravite, cout_estime, jours_retard,
            date_incident, statut
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chantier_id,
        titre,
        description,
        gravite,
        cout_estime,
        jours_retard,
        date.today().isoformat(),
        statut
    ))

    conn.commit()
    conn.close()


def supprimer_incident_db(incident_id):
    conn = connecter_db()

    conn.execute(
        "DELETE FROM incidents WHERE id = ?",
        (incident_id,)
    )

    conn.commit()
    conn.close()


# ============================================================
# FONCTIONS PROBABILISTES
# ============================================================

def percentile(valeurs, p):
    if not valeurs:
        return 0.0

    valeurs_triees = sorted(valeurs)

    position = (len(valeurs_triees) - 1) * p / 100

    bas = int(math.floor(position))
    haut = int(math.ceil(position))

    if bas == haut:
        return valeurs_triees[bas]

    poids = position - bas

    return (
        valeurs_triees[bas] * (1 - poids)
        + valeurs_triees[haut] * poids
    )


def probabilite_depassement(
    budget, cout_estime, incertitude
):
    if budget <= 0 or cout_estime < 0:
        return None

    ecart_type = max(
        abs(cout_estime) * incertitude,
        1.0
    )

    z = (budget - cout_estime) / ecart_type

    p = (1 - NormalDist().cdf(z)) * 100

    return max(0.0, min(100.0, p))


def probabilite_retard(
    duree_prevue, duree_estimee, incertitude
):
    if duree_prevue <= 0 or duree_estimee < 0:
        return None

    ecart_type = max(
        abs(duree_estimee) * incertitude,
        1.0
    )

    z = (duree_prevue - duree_estimee) / ecart_type

    p = (1 - NormalDist().cdf(z)) * 100

    return max(0.0, min(100.0, p))


def tirer_valeur_probabiliste(
    distribution,
    minimum,
    valeur_centrale,
    maximum,
    ecart_type=0.15
):
    """
    Génère une valeur selon la distribution choisie.

    Triangulaire :
        minimum, mode, maximum.

    Normale :
        moyenne = valeur_centrale ;
        écart-type calculé à partir de l'intervalle fourni.
    """

    minimum = float(minimum)
    valeur_centrale = float(valeur_centrale)
    maximum = float(maximum)

    if minimum < 0 or maximum < minimum:
        raise ValueError(
            "Les bornes doivent être positives "
            "et le maximum supérieur au minimum."
        )

    if not minimum <= valeur_centrale <= maximum:
        raise ValueError(
            "La valeur centrale doit se trouver "
            "entre le minimum et le maximum."
        )

    if distribution == "Triangulaire":
        return random.triangular(
            minimum,
            maximum,
            valeur_centrale
        )

    if distribution == "Normale":
        sigma = max(
            (maximum - minimum) / 6,
            abs(valeur_centrale) * ecart_type,
            0.000001
        )

        valeur = random.gauss(
            valeur_centrale,
            sigma
        )

        # Les coûts et durées négatifs sont impossibles.
        return max(0.0, valeur)

    raise ValueError("Distribution probabiliste inconnue.")


def simulation_probabiliste_avancee(
    budget,
    duree_prevue,
    cout_min,
    cout_central,
    cout_max,
    duree_min,
    duree_centrale,
    duree_max,
    distribution="Triangulaire",
    iterations=10000
):
    """
    Simulation de Monte-Carlo utilisant une distribution
    triangulaire ou normale pour les coûts et les durées.

    Les valeurs minimales, centrales et maximales doivent
    être définies par l'utilisateur.
    """

    if budget <= 0 or duree_prevue <= 0:
        return None

    iterations = max(
        100,
        min(int(iterations), 100000)
    )

    couts = []
    durees = []

    for _ in range(iterations):

        cout = tirer_valeur_probabiliste(
            distribution,
            cout_min,
            cout_central,
            cout_max
        )

        duree = tirer_valeur_probabiliste(
            distribution,
            duree_min,
            duree_centrale,
            duree_max
        )

        couts.append(cout)
        durees.append(duree)

    return {
        "distribution": distribution,
        "iterations": iterations,
        "cout_moyen": mean(couts),
        "cout_mediane": median(couts),
        "cout_p50": percentile(couts, 50),
        "cout_p80": percentile(couts, 80),
        "cout_p90": percentile(couts, 90),
        "cout_p95": percentile(couts, 95),
        "duree_moyenne": mean(durees),
        "duree_mediane": median(durees),
        "duree_p50": percentile(durees, 50),
        "duree_p80": percentile(durees, 80),
        "duree_p90": percentile(durees, 90),
        "duree_p95": percentile(durees, 95),
        "prob_cout": (
            sum(c > budget for c in couts)
            / len(couts) * 100
        ),
        "prob_delai": (
            sum(d > duree_prevue for d in durees)
            / len(durees) * 100
        ),
        "couts": couts,
        "durees": durees
    }


# ============================================================
# SIMULATION MONTE-CARLO CLASSIQUE
# ============================================================

def simulation_monte_carlo(
    budget,
    duree_prevue,
    depenses,
    avancement,
    iterations=5000,
    incertitude_cout=0.15,
    incertitude_delai=0.20,
    retard_incidents=0
):
    if budget <= 0 or duree_prevue <= 0:
        return None

    iterations = max(
        100,
        min(int(iterations), 100000)
    )

    avancement = max(
        1.0,
        min(100.0, float(avancement))
    )

    progression = avancement / 100.0
    depenses = max(0.0, float(depenses))

    cout_central = (
        depenses / progression
        if depenses > 0
        else float(budget)
    )

    duree_centrale = float(duree_prevue) / progression

    couts = []
    durees = []

    for _ in range(iterations):

        facteur_cout = max(
            0.10,
            random.gauss(1.0, incertitude_cout)
        )

        facteur_delai = max(
            0.10,
            random.gauss(1.0, incertitude_delai)
        )

        couts.append(
            max(0.0, cout_central * facteur_cout)
        )

        durees.append(
            max(
                0.0,
                duree_centrale * facteur_delai
                + max(0, retard_incidents)
            )
        )

    return {
        "cout_moyen": mean(couts),
        "cout_mediane": median(couts),
        "cout_p50": percentile(couts, 50),
        "cout_p80": percentile(couts, 80),
        "cout_p90": percentile(couts, 90),
        "cout_p95": percentile(couts, 95),
        "duree_moyenne": mean(durees),
        "duree_mediane": median(durees),
        "duree_p50": percentile(durees, 50),
        "duree_p80": percentile(durees, 80),
        "duree_p90": percentile(durees, 90),
        "duree_p95": percentile(durees, 95),
        "prob_cout": (
            sum(c > budget for c in couts)
            / len(couts) * 100
        ),
        "prob_delai": (
            sum(d > duree_prevue for d in durees)
            / len(durees) * 100
        ),
        "couts": couts,
        "durees": durees
    }


# ============================================================
# PRÉVISIONS FINANCIÈRES SUR CINQ ANS
# ============================================================

def simulation_financiere_cinq_ans(
    budget_initial,
    depenses_initiales,
    inflation_annuelle,
    croissance_risque,
    annees=5,
    iterations=5000
):
    annees = max(1, min(int(annees), 5))

    iterations = max(
        100,
        min(int(iterations), 100000)
    )

    inflation = inflation_annuelle / 100
    croissance = croissance_risque / 100

    budget_initial = max(
        0.0,
        float(budget_initial)
    )

    depenses_initiales = max(
        0.0,
        float(depenses_initiales)
    )

    couts_annuels = []
    resultats_annuels = []

    cout_initial = max(
        budget_initial,
        depenses_initiales
    )

    for annee in range(1, annees + 1):

        cout_central = (
            cout_initial * ((1 + inflation) ** annee)
        )

        reserve = cout_central * max(
            0.0,
            croissance
        )

        couts_annuels.append({
            "Année": annee,
            "Coût estimé": cout_central,
            "Réserve risques": reserve,
            "Coût total estimé": cout_central + reserve
        })

        couts_simules = []

        for _ in range(iterations):

            facteur_inflation = max(
                0.50,
                random.gauss(1 + inflation, 0.03)
            )

            facteur_risque = max(
                0.50,
                random.gauss(
                    1 + max(0.0, croissance),
                    0.08
                )
            )

            cout_simule = (
                cout_initial
                * ((1 + inflation) ** annee)
                * facteur_inflation
                * facteur_risque
            )

            couts_simules.append(
                max(0.0, cout_simule)
            )

        resultats_annuels.append({
            "Année": annee,
            "Coût moyen simulé": mean(couts_simules),
            "Médiane": median(couts_simules),
            "P90": percentile(couts_simules, 90),
            "P95": percentile(couts_simules, 95)
        })

    return couts_annuels, resultats_annuels


# ============================================================
# FONCTION DE CALCUL DU SCORE DE RISQUE
# ============================================================

def evaluer_risque(probabilite, impact):
    """
    probabilite : valeur entre 0 et 1.
    impact : valeur entre 1 et 5.
    """

    score = float(probabilite) * 100 * float(impact)

    if score >= 300:
        niveau = "Critique"
    elif score >= 150:
        niveau = "Élevé"
    elif score >= 50:
        niveau = "Modéré"
    else:
        niveau = "Faible"

    return score, niveau


# ============================================================
# GÉNÉRATION DU DIAGRAMME DE GANTT EN HTML
# ============================================================

def generer_gantt_html(activites):
    """
    Construit une représentation visuelle simple du planning.
    Aucun logiciel graphique supplémentaire n'est nécessaire.
    """

    if not activites:
        return "<p>Aucune activité planifiée.</p>"

    dates = []

    for activite in activites:
        try:
            debut = date.fromisoformat(
                activite["date_debut_prevue"]
            )

            duree = max(
                1,
                int(float(activite.get("duree_prevue") or 1))
            )

            fin = debut + timedelta(days=duree)

            dates.extend([debut, fin])

        except (ValueError, TypeError):
            continue

    if not dates:
        return "<p>Les dates des activités sont invalides.</p>"

    debut_global = min(dates)
    fin_global = max(dates)

    duree_globale = max(
        1,
        (fin_global - debut_global).days
    )

    html = """
    <style>
    .gantt-container {
        font-family: Arial, sans-serif;
        width: 100%;
        overflow-x: auto;
    }
    .gantt-row {
        display: grid;
        grid-template-columns: 180px minmax(400px, 1fr);
        gap: 10px;
        align-items: center;
        margin-bottom: 12px;
    }
    .gantt-name {
        font-size: 13px;
        overflow-wrap: anywhere;
    }
    .gantt-track {
        position: relative;
        height: 28px;
        background: #edf2f7;
        border-radius: 5px;
        overflow: hidden;
    }
    .gantt-bar {
        position: absolute;
        height: 100%;
        border-radius: 5px;
        color: white;
        font-size: 11px;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        white-space: nowrap;
    }
    .gantt-date {
        font-size: 12px;
        color: #475569;
        margin-bottom: 12px;
    }
    </style>
    <div class="gantt-container">
    """

    html += (
        '<div class="gantt-date">'
        f'Période : {debut_global.isoformat()} '
        f'→ {fin_global.isoformat()}'
        '</div>'
    )

    couleurs = {
        "À faire": "#64748b",
        "En cours": "#2563eb",
        "Terminé": "#15803d",
        "En retard": "#dc2626",
        "Suspendu": "#d97706"
    }

    for activite in activites:

        try:
            debut = date.fromisoformat(
                activite["date_debut_prevue"]
            )

            duree = max(
                1,
                int(float(activite.get("duree_prevue") or 1))
            )

        except (ValueError, TypeError):
            continue

        decalage = (
            debut - debut_global
        ).days

        gauche = (
            decalage / duree_globale * 100
        )

        largeur = (
            duree / duree_globale * 100
        )

        largeur = min(
            largeur,
            max(0.5, 100 - gauche)
        )

        statut = activite.get("statut") or "À faire"
        couleur = couleurs.get(statut, "#2563eb")

        progression = float(
            activite.get("avancement") or 0
        )

        nom = str(
            activite.get("nom") or "Activité"
        )

        # Échappement minimal du texte HTML.
        nom_html = (
            nom.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

        html += f"""
        <div class="gantt-row">
            <div class="gantt-name">
                <strong>{nom_html}</strong><br>
                <small>{statut} — {progression:.0f} %</small>
            </div>
            <div class="gantt-track">
                <div class="gantt-bar"
                     style="left:{gauche:.3f}%;
                            width:{largeur:.3f}%;
                            background:{couleur};">
                    {duree} j
                </div>
            </div>
        </div>
        """

    html += "</div>"

    return html


# ============================================================
# EXPORT PDF
# ============================================================

def creer_pdf(titre, contenu):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle
        )
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from xml.sax.saxutils import escape

        tampon = io.BytesIO()

        document = SimpleDocTemplate(
            tampon,
            pagesize=A4,
            rightMargin=35,
            leftMargin=35,
            topMargin=35,
            bottomMargin=35
        )

        styles = getSampleStyleSheet()

        elements = [
            Paragraph(
                escape(str(titre)),
                styles["Title"]
            ),
            Spacer(1, 15)
        ]

        lignes = [["Indicateur", "Valeur"]]

        for cle, valeur in contenu.items():
            lignes.append([
                Paragraph(
                    escape(str(cle)),
                    styles["BodyText"]
                ),
                Paragraph(
                    escape(str(valeur)),
                    styles["BodyText"]
                )
            ])

        tableau = Table(
            lignes,
            colWidths=[230, 250],
            repeatRows=1
        )

        tableau.setStyle(TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#164e63")
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP"
            ),
            (
                "PADDING",
                (0, 0),
                (-1, -1),
                7
            )
        ]))

        elements.append(tableau)
        document.build(elements)

        return tampon.getvalue()

    except ImportError:
        return None


# ============================================================
# EXPORT EXCEL
# ============================================================

def creer_excel(donnees, nom_feuille="Rapport"):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter

        tampon = io.BytesIO()

        classeur = Workbook()
        feuille = classeur.active
        feuille.title = nom_feuille[:31]

        if not donnees:
            feuille.append(["Aucune donnée disponible"])

        else:
            entetes = list(donnees[0].keys())
            feuille.append(entetes)

            for ligne in donnees:
                feuille.append([
                    ligne.get(entete, "")
                    for entete in entetes
                ])

            for cellule in feuille[1]:
                cellule.font = Font(
                    bold=True,
                    color="FFFFFF"
                )

                cellule.fill = PatternFill(
                    fill_type="solid",
                    fgColor="164E63"
                )

            feuille.freeze_panes = "A2"
            feuille.auto_filter.ref = feuille.dimensions

            for colonne in feuille.columns:

                largeur = max(
                    len(str(cellule.value or ""))
                    for cellule in colonne
                )

                lettre = get_column_letter(
                    colonne[0].column
                )

                feuille.column_dimensions[lettre].width = min(
                    largeur + 3,
                    40
                )

        classeur.save(tampon)

        return tampon.getvalue()

    except ImportError:
        return None


# ============================================================
# FIN DE LA PARTIE 1/2
#
# La PARTIE 2 contiendra :
# - Navigation complète
# - Tableau de bord
# - Gestion des chantiers et dépenses
# - Suivi de l'avancement et des délais
# - Analyse probabiliste avancée
# - Risques par activité
# - Diagramme de Gantt
# - Gestion des incidents
# - Analyses budgétaires
# - Monte-Carlo
# - Prévisions sur cinq ans
# - Rapports PDF et Excel
#
# NE PAS EXÉCUTER AVANT D'AVOIR AJOUTÉ LA PARTIE 2/2.
# ============================================================
# ============================================================
# CIVI-PREDICT
# PARTIE 2/2 — INTERFACE ET FONCTIONNALITÉS
# À COLLER À LA SUITE DE LA PARTIE 1/2
# ============================================================


# ============================================================
# TITRE ET PRÉSENTATION
# ============================================================

st.title("🏗️ CIVI-PREDICT")

st.markdown(
    """
    ### Analyse probabiliste des risques dans les projets de construction

    Gestion des chantiers, suivi budgétaire, planification des
    travaux et analyse probabiliste des risques.
    """
)

st.divider()


# ============================================================
# NAVIGATION
# ============================================================

pages = [
    "Tableau de bord",
    "Créer un chantier",
    "Liste des chantiers",
    "Gestion des dépenses",
    "Suivi de l'avancement",
    "Suivi des délais",
    "Gestion des risques",
    "Risques par activité",
    "Diagramme de Gantt",
    "Gestion des incidents",
    "Analyse budgétaire",
    "Analyse probabiliste",
    "Analyse probabiliste avancée",
    "Simulation Monte-Carlo",
    "Prévisions sur 5 ans",
    "Rapports PDF et Excel"
]

with st.sidebar:
    st.title("🏗️ CIVI-PREDICT")

    st.caption(
        "Gestion et analyse des risques des projets de construction"
    )

    page = st.radio(
        "Navigation",
        pages,
        key="navigation_principale"
    )

    st.divider()

    st.markdown("### Fonctionnalités")

    st.markdown(
        """
        - Gestion des chantiers
        - Suivi des dépenses
        - Suivi des délais
        - Analyse des risques
        - Simulation de Monte-Carlo
        - Diagramme de Gantt
        - Exports PDF et Excel
        """
    )

    st.divider()

    st.caption("CIVI-PREDICT — Version améliorée")


# ============================================================
# DONNÉES COMMUNES
# ============================================================

chantiers = lire_chantiers()

if chantiers:
    chantier_options = {
        f"{c['nom']} — ID {c['id']}": c["id"]
        for c in chantiers
    }

    noms_chantiers = list(chantier_options.keys())

else:
    chantier_options = {}
    noms_chantiers = []


def choisir_chantier(label="Sélectionner un chantier"):
    if not chantiers:
        st.warning(
            "Aucun chantier enregistré. "
            "Commence par créer un chantier."
        )
        return None

    selection = st.selectbox(
        label,
        noms_chantiers,
        key=f"select_chantier_{page}"
    )

    return chantier_options[selection]


def afficher_tableau(donnees, message_vide="Aucune donnée disponible."):
    if donnees:
        st.dataframe(
            donnees,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info(message_vide)


def statut_risque(probabilite, impact):
    score, niveau = evaluer_risque(probabilite, impact)

    return score, niveau


def creer_donnees_rapport(chantier_id):
    chantier = obtenir_chantier(chantier_id)

    if not chantier:
        return {}

    depenses = total_depenses(chantier_id)
    avancement = dernier_avancement(chantier_id)

    budget = float(chantier.get("budget") or 0)
    duree = float(chantier.get("duree") or 0)

    return {
        "Chantier": chantier.get("nom", ""),
        "Lieu": chantier.get("lieu", ""),
        "Responsable": chantier.get("responsable", ""),
        "Date de démarrage": chantier.get("date_demarrage", ""),
        "Durée prévue (jours)": duree,
        "Budget prévu": fcfa(budget),
        "Dépenses enregistrées": fcfa(depenses),
        "Budget restant": fcfa(budget - depenses),
        "Avancement actuel": f"{avancement:.1f} %",
        "Date du rapport": date.today().isoformat()
    }


# ============================================================
# 1. TABLEAU DE BORD
# ============================================================

if page == "Tableau de bord":

    st.header("📊 Tableau de bord général")

    if not chantiers:
        st.info(
            "Bienvenue dans CIVI-PREDICT ! "
            "Crée ton premier chantier pour commencer."
        )

        st.markdown(
            """
            ### Ce que tu peux faire avec l'application

            1. Enregistrer un chantier.
            2. Définir son budget et sa durée.
            3. Enregistrer les dépenses.
            4. Suivre l'avancement des travaux.
            5. Identifier les risques.
            6. Simuler les dépassements de coûts et de délais.
            7. Planifier les activités avec le diagramme de Gantt.
            """
        )

    else:
        total_chantiers = len(chantiers)

        budget_global = sum(
            float(c.get("budget") or 0)
            for c in chantiers
        )

        depenses_globales = sum(
            total_depenses(c["id"])
            for c in chantiers
        )

        budget_restant = budget_global - depenses_globales

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Nombre de chantiers",
            total_chantiers
        )

        col2.metric(
            "Budget global",
            fcfa(budget_global)
        )

        col3.metric(
            "Dépenses globales",
            fcfa(depenses_globales)
        )

        col4.metric(
            "Budget restant",
            fcfa(budget_restant)
        )

        if budget_global > 0:
            consommation = (
                depenses_globales / budget_global
            ) * 100

            consommation = max(
                0.0,
                min(100.0, consommation)
            )

            st.subheader("Consommation budgétaire globale")

            st.progress(
                consommation / 100
            )

            st.write(
                f"{consommation:.1f} % du budget global "
                "a été consommé."
            )

        st.divider()

        st.subheader("État des chantiers")

        lignes = []

        for c in chantiers:
            depenses = total_depenses(c["id"])
            budget = float(c.get("budget") or 0)
            avancement = dernier_avancement(c["id"])

            reste = budget - depenses

            consommation = (
                depenses / budget * 100
                if budget > 0
                else 0
            )

            lignes.append({
                "Chantier": c.get("nom", ""),
                "Lieu": c.get("lieu", ""),
                "Responsable": c.get("responsable", ""),
                "Durée prévue (jours)": c.get("duree", 0),
                "Budget": fcfa(budget),
                "Dépenses": fcfa(depenses),
                "Reste": fcfa(reste),
                "Budget consommé (%)": round(consommation, 2),
                "Avancement (%)": round(avancement, 2)
            })

        afficher_tableau(lignes)

        st.subheader("Répartition des budgets")

        try:
            import pandas as pd
            import matplotlib.pyplot as plt

            donnees_graphique = pd.DataFrame({
                "Chantier": [
                    c.get("nom", "")
                    for c in chantiers
                ],
                "Budget": [
                    float(c.get("budget") or 0)
                    for c in chantiers
                ]
            })

            donnees_graphique = donnees_graphique.set_index(
                "Chantier"
            )

            fig, ax = plt.subplots()

            donnees_graphique["Budget"].plot(
                kind="bar",
                ax=ax
            )

            ax.set_ylabel("Budget en FCFA")
            ax.set_title("Budget prévu par chantier")

            plt.xticks(rotation=35, ha="right")
            plt.tight_layout()

            st.pyplot(fig)
            plt.close(fig)

        except ImportError:
            st.info(
                "Le graphique nécessite pandas et matplotlib. "
                "Les autres fonctions restent disponibles."
            )


# ============================================================
# 2. CRÉER UN CHANTIER
# ============================================================

elif page == "Créer un chantier":

    st.header("➕ Créer un chantier")

    with st.form("form_creation_chantier"):

        nom = st.text_input(
            "Nom du chantier"
        )

        lieu = st.text_input(
            "Lieu du chantier"
        )

        responsable = st.text_input(
            "Nom du responsable"
        )

        col1, col2 = st.columns(2)

        with col1:
            duree = st.number_input(
                "Durée prévue (jours)",
                min_value=1.0,
                value=30.0,
                step=1.0
            )

        with col2:
            budget = st.number_input(
                "Budget prévu (FCFA)",
                min_value=0.0,
                value=10000000.0,
                step=100000.0
            )

        date_demarrage = st.date_input(
            "Date de démarrage",
            value=date.today()
        )

        enregistrer = st.form_submit_button(
            "Enregistrer le chantier"
        )

    if enregistrer:

        if not nom.strip():
            st.error(
                "Le nom du chantier est obligatoire."
            )

        elif budget <= 0:
            st.error(
                "Le budget doit être supérieur à zéro."
            )

        else:
            ajouter_chantier_db(
                nom.strip(),
                lieu.strip(),
                responsable.strip(),
                duree,
                budget,
                date_demarrage
            )

            st.success(
                "Chantier enregistré avec succès."
            )

            st.rerun()


# ============================================================
# 3. LISTE DES CHANTIERS
# ============================================================

elif page == "Liste des chantiers":

    st.header("📋 Liste des chantiers")

    if not chantiers:
        st.info("Aucun chantier enregistré.")

    else:
        donnees = []

        for c in chantiers:
            depenses = total_depenses(c["id"])
            budget = float(c.get("budget") or 0)

            donnees.append({
                "ID": c["id"],
                "Nom": c.get("nom", ""),
                "Lieu": c.get("lieu", ""),
                "Responsable": c.get("responsable", ""),
                "Durée prévue": c.get("duree", 0),
                "Budget": fcfa(budget),
                "Dépenses": fcfa(depenses),
                "Reste": fcfa(budget - depenses),
                "Date de démarrage": c.get("date_demarrage", "")
            })

        afficher_tableau(donnees)

        st.divider()

        st.subheader("Modifier un chantier")

        selection = choisir_chantier(
            "Choisir le chantier à modifier"
        )

        if selection is not None:

            chantier = obtenir_chantier(selection)

            if chantier:

                with st.form("form_modifier_chantier"):

                    nom_mod = st.text_input(
                        "Nom",
                        value=chantier.get("nom") or "",
                        key="mod_nom"
                    )

                    lieu_mod = st.text_input(
                        "Lieu",
                        value=chantier.get("lieu") or "",
                        key="mod_lieu"
                    )

                    resp_mod = st.text_input(
                        "Responsable",
                        value=chantier.get("responsable") or "",
                        key="mod_resp"
                    )

                    duree_mod = st.number_input(
                        "Durée prévue (jours)",
                        min_value=1.0,
                        value=max(
                            1.0,
                            float(chantier.get("duree") or 1)
                        ),
                        key="mod_duree"
                    )

                    budget_mod = st.number_input(
                        "Budget (FCFA)",
                        min_value=0.0,
                        value=max(
                            0.0,
                            float(chantier.get("budget") or 0)
                        ),
                        step=100000.0,
                        key="mod_budget"
                    )

                    try:
                        date_initiale = date.fromisoformat(
                            chantier.get("date_demarrage")
                            or date.today().isoformat()
                        )
                    except ValueError:
                        date_initiale = date.today()

                    date_mod = st.date_input(
                        "Date de démarrage",
                        value=date_initiale,
                        key="mod_date"
                    )

                    modifier = st.form_submit_button(
                        "Enregistrer les modifications"
                    )

                if modifier:

                    if not nom_mod.strip():
                        st.error(
                            "Le nom du chantier est obligatoire."
                        )

                    else:
                        modifier_chantier_db(
                            selection,
                            nom_mod.strip(),
                            lieu_mod.strip(),
                            resp_mod.strip(),
                            duree_mod,
                            budget_mod,
                            date_mod
                        )

                        st.success(
                            "Chantier modifié."
                        )

                        st.rerun()

        st.divider()

        st.subheader("Supprimer un chantier")

        st.warning(
            "La suppression d'un chantier entraîne aussi "
            "la suppression de ses dépenses, incidents, "
            "avancements, risques et activités associés."
        )

        chantier_supp = choisir_chantier(
            "Choisir le chantier à supprimer"
        )

        if chantier_supp is not None:

            confirmation = st.checkbox(
                "Je confirme vouloir supprimer ce chantier.",
                key="confirmation_suppression_chantier"
            )

            if st.button(
                "Supprimer définitivement",
                type="primary",
                disabled=not confirmation
            ):
                supprimer_chantier_db(chantier_supp)

                st.success(
                    "Le chantier et ses données associées "
                    "ont été supprimés."
                )

                st.rerun()


# ============================================================
# 4. GESTION DES DÉPENSES
# ============================================================

elif page == "Gestion des dépenses":

    st.header("💰 Gestion des dépenses")

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(chantier_id)

        budget = float(
            chantier.get("budget") or 0
        )

        depenses = total_depenses(chantier_id)

        st.metric(
            "Budget prévu",
            fcfa(budget)
        )

        st.metric(
            "Dépenses cumulées",
            fcfa(depenses)
        )

        st.metric(
            "Solde budgétaire",
            fcfa(budget - depenses)
        )

        if budget > 0:

            consommation = depenses / budget

            st.progress(
                max(0.0, min(1.0, consommation))
            )

            st.caption(
                f"Budget consommé : "
                f"{consommation * 100:.1f} %"
            )

        st.divider()

        st.subheader("Enregistrer une dépense")

        with st.form("form_depense"):

            categorie = st.selectbox(
                "Catégorie",
                [
                    "Matériaux",
                    "Main-d'œuvre",
                    "Transport",
                    "Équipement",
                    "Location",
                    "Études",
                    "Sécurité",
                    "Autres"
                ]
            )

            montant = st.number_input(
                "Montant (FCFA)",
                min_value=0.0,
                value=10000.0,
                step=1000.0
            )

            description = st.text_area(
                "Description de la dépense"
            )

            date_depense = st.date_input(
                "Date de la dépense",
                value=date.today()
            )

            enregistrer_depense = st.form_submit_button(
                "Enregistrer la dépense"
            )

        if enregistrer_depense:

            if montant <= 0:
                st.error(
                    "Le montant doit être supérieur à zéro."
                )

            else:
                ajouter_depense_db(
                    chantier_id,
                    categorie,
                    montant,
                    description,
                    date_depense
                )

                st.success(
                    "Dépense enregistrée."
                )

                st.rerun()

        st.divider()

        st.subheader("Historique des dépenses")

        depenses_lues = lire_depenses(chantier_id)

        afficher_tableau([
            {
                "ID": d["id"],
                "Catégorie": d.get("categorie", ""),
                "Montant": fcfa(d.get("montant", 0)),
                "Description": d.get("description", ""),
                "Date": d.get("date_depense", "")
            }
            for d in depenses_lues
        ])

        if depenses_lues:

            ids_depenses = [
                d["id"] for d in depenses_lues
            ]

            depense_a_supprimer = st.selectbox(
                "Sélectionner une dépense à supprimer",
                ids_depenses,
                key="depense_a_supprimer"
            )

            confirmer_depense = st.checkbox(
                "Confirmer la suppression de cette dépense",
                key="confirmer_suppression_depense"
            )

            if st.button(
                "Supprimer la dépense",
                disabled=not confirmer_depense
            ):
                supprimer_depense_db(
                    depense_a_supprimer
                )

                st.success(
                    "Dépense supprimée."
                )

                st.rerun()


# ============================================================
# 5. SUIVI DE L'AVANCEMENT
# ============================================================

elif page == "Suivi de l'avancement":

    st.header("📈 Suivi de l'avancement des travaux")

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        avancement_actuel = dernier_avancement(
            chantier_id
        )

        st.metric(
            "Dernier avancement enregistré",
            f"{avancement_actuel:.1f} %"
        )

        st.progress(
            max(
                0.0,
                min(1.0, avancement_actuel / 100)
            )
        )

        st.divider()

        with st.form("form_avancement"):

            pourcentage = st.number_input(
                "Avancement total du chantier (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(avancement_actuel),
                step=5.0
            )

            description = st.text_area(
                "Travaux réalisés et observations"
            )

            date_suivi = st.date_input(
                "Date du suivi",
                value=date.today()
            )

            enregistrer_avancement = st.form_submit_button(
                "Enregistrer l'avancement"
            )

        if enregistrer_avancement:

            if pourcentage < avancement_actuel:
                st.warning(
                    "L'avancement enregistré est inférieur "
                    "au dernier avancement. Vérifie les valeurs."
                )

            ajouter_avancement_db(
                chantier_id,
                pourcentage,
                description,
                date_suivi
            )

            st.success(
                "Avancement enregistré."
            )

            st.rerun()

        st.divider()

        st.subheader("Historique de l'avancement")

        historique = lire_avancements(
            chantier_id
        )

        afficher_tableau([
            {
                "Date": a.get("date_avancement", ""),
                "Avancement (%)": a.get("pourcentage", 0),
                "Description": a.get("description", "")
            }
            for a in historique
        ])

        if len(historique) >= 2:

            try:
                import pandas as pd
                import matplotlib.pyplot as plt

                df = pd.DataFrame(historique)

                df["date_avancement"] = pd.to_datetime(
                    df["date_avancement"],
                    errors="coerce"
                )

                df = df.dropna(
                    subset=["date_avancement"]
                )

                if not df.empty:

                    fig, ax = plt.subplots()

                    ax.plot(
                        df["date_avancement"],
                        df["pourcentage"],
                        marker="o"
                    )

                    ax.set_title(
                        "Évolution de l'avancement"
                    )

                    ax.set_xlabel("Date")
                    ax.set_ylabel("Avancement (%)")

                    ax.set_ylim(0, 100)

                    plt.xticks(rotation=30)
                    plt.tight_layout()

                    st.pyplot(fig)
                    plt.close(fig)

            except ImportError:
                st.info(
                    "Le graphique nécessite pandas et matplotlib."
                )


# ============================================================
# 6. SUIVI DES DÉLAIS
# ============================================================

elif page == "Suivi des délais":

    st.header("⏱️ Suivi des délais")

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(
            chantier_id
        )

        duree_prevue = float(
            chantier.get("duree") or 0
        )

        avancement = dernier_avancement(
            chantier_id
        )

        try:
            debut = date.fromisoformat(
                chantier.get("date_demarrage")
                or date.today().isoformat()
            )

            jours_ecoules = max(
                0,
                (date.today() - debut).days
            )

        except ValueError:
            debut = date.today()
            jours_ecoules = 0

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Durée prévue",
            f"{duree_prevue:.0f} jours"
        )

        col2.metric(
            "Jours écoulés",
            f"{jours_ecoules} jours"
        )

        col3.metric(
            "Avancement",
            f"{avancement:.1f} %"
        )

        if duree_prevue > 0:

            avancement_theorique = min(
                100.0,
                jours_ecoules / duree_prevue * 100
            )

            ecart = avancement - avancement_theorique

            st.write(
                f"Avancement théorique estimé : "
                f"{avancement_theorique:.1f} %"
            )

            st.write(
                f"Écart entre l'avancement réel et théorique : "
                f"{ecart:+.1f} points"
            )

            if ecart < -10:
                st.error(
                    "Le chantier présente un retard potentiel "
                    "par rapport à l'avancement théorique."
                )

            elif ecart < 0:
                st.warning(
                    "L'avancement est inférieur au rythme théorique."
                )

            else:
                st.success(
                    "L'avancement est conforme ou supérieur "
                    "au rythme théorique."
                )

            st.info(
                "Cette comparaison suppose une progression "
                "linéaire dans le temps. Un véritable planning "
                "par activités donnera une analyse plus précise."
            )

        st.divider()

        st.subheader("Activités enregistrées")

        activites = lire_activites(
            chantier_id
        )

        afficher_tableau([
            {
                "Activité": a.get("nom", ""),
                "Début prévu": a.get("date_debut_prevue", ""),
                "Durée prévue (jours)": a.get("duree_prevue", 0),
                "Début réel": a.get("date_debut_reelle", ""),
                "Durée réelle (jours)": a.get("duree_reelle", ""),
                "Avancement (%)": a.get("avancement", 0),
                "Statut": a.get("statut", "")
            }
            for a in activites
        ])


# ============================================================
# 7. GESTION DES RISQUES
# ============================================================

elif page == "Gestion des risques":

    st.header("⚠️ Gestion des risques du chantier")

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        st.subheader("Enregistrer un risque")

        with st.form("form_risque_general"):

            nom_risque = st.text_input(
                "Nom du risque"
            )

            probabilite = st.slider(
                "Probabilité estimée (%)",
                min_value=0,
                max_value=100,
                value=30
            )

            impact = st.slider(
                "Impact potentiel (1 à 5)",
                min_value=1,
                max_value=5,
                value=3
            )

            prevention = st.text_area(
                "Mesures de prévention"
            )

            statut = st.selectbox(
                "Statut",
                [
                    "À surveiller",
                    "En cours de traitement",
                    "Maîtrisé",
                    "Réalisé"
                ]
            )

            enregistrer_risque = st.form_submit_button(
                "Enregistrer le risque"
            )

        if enregistrer_risque:

            if not nom_risque.strip():
                st.error(
                    "Le nom du risque est obligatoire."
                )

            else:
                ajouter_risque_db(
                    chantier_id,
                    nom_risque.strip(),
                    probabilite / 100,
                    impact,
                    prevention,
                    statut,
                    None
                )

                st.success(
                    "Risque enregistré."
                )

                st.rerun()

        st.divider()

        st.subheader("Registre des risques")

        risques = lire_risques(
            chantier_id
        )

        lignes = []

        for r in risques:

            p = float(
                r.get("probabilite") or 0
            )

            # Les anciennes données peuvent utiliser
            # une probabilité entre 0 et 100.
            if p > 1:
                p = p / 100

            i = float(
                r.get("impact") or 1
            )

            score, niveau = evaluer_risque(
                p,
                i
            )

            lignes.append({
                "ID": r["id"],
                "Risque": r.get("nom", ""),
                "Probabilité (%)": round(p * 100, 1),
                "Impact": i,
                "Score": round(score, 1),
                "Niveau": niveau,
                "Activité": r.get("nom_activite") or "Général",
                "Prévention": r.get("mesure_prevention", ""),
                "Statut": r.get("statut", "")
            })

        afficher_tableau(lignes)

        if risques:

            ids_risques = [
                r["id"] for r in risques
            ]

            risque_supp = st.selectbox(
                "Risque à supprimer",
                ids_risques,
                key="risque_supp_general"
            )

            confirmer_risque = st.checkbox(
                "Confirmer la suppression du risque",
                key="confirmer_risque_general"
            )

            if st.button(
                "Supprimer le risque",
                disabled=not confirmer_risque
            ):
                supprimer_risque_db(
                    risque_supp
                )

                st.success(
                    "Risque supprimé."
                )

                st.rerun()
   # ============================================================
# 8. RISQUES PAR ACTIVITÉ — NOUVELLE FONCTIONNALITÉ B
# ============================================================

elif page == "Risques par activité":

    st.header("🏗️ Analyse des risques par activité")

    st.write(
        "Associe chaque risque à une activité précise du chantier : "
        "terrassement, fondations, poteaux, poutres, maçonnerie, toiture, "
        "ou toute autre activité."
    )

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        activites = lire_activites(
            chantier_id
        )

        st.subheader("Enregistrer un risque lié à une activité")

        if not activites:

            st.warning(
                "Aucune activité n'est encore enregistrée. "
                "Ajoute d'abord des activités dans la rubrique "
                "Diagramme de Gantt."
            )

        else:

            activites_options = {
                f"{a['nom']} — ID {a['id']}": a["id"]
                for a in activites
            }

            with st.form("form_risque_activite"):

                nom_risque = st.text_input(
                    "Nom du risque"
                )

                activite_selection = st.selectbox(
                    "Activité concernée",
                    list(activites_options.keys())
                )

                probabilite = st.slider(
                    "Probabilité d'apparition (%)",
                    0,
                    100,
                    30,
                    key="prob_activite"
                )

                impact = st.slider(
                    "Impact (1 = faible, 5 = très élevé)",
                    1,
                    5,
                    3,
                    key="impact_activite"
                )

                prevention = st.text_area(
                    "Mesures de prévention"
                )

                statut = st.selectbox(
                    "Statut du risque",
                    [
                        "À surveiller",
                        "En cours de traitement",
                        "Maîtrisé",
                        "Réalisé"
                    ],
                    key="statut_risque_activite"
                )

                enregistrer = st.form_submit_button(
                    "Enregistrer le risque lié à l'activité"
                )

            if enregistrer:

                if not nom_risque.strip():
                    st.error(
                        "Le nom du risque est obligatoire."
                    )

                else:

                    activite_id = activites_options[
                        activite_selection
                    ]

                    ajouter_risque_db(
                        chantier_id,
                        nom_risque.strip(),
                        probabilite / 100,
                        impact,
                        prevention,
                        statut,
                        activite_id
                    )

                    st.success(
                        "Risque associé à l'activité enregistré."
                    )

                    st.rerun()

        st.divider()

        st.subheader("Risques enregistrés")

        risques = lire_risques(
            chantier_id
        )

        risques_activites = [
            r for r in risques
            if r.get("activite_id") is not None
        ]

        afficher_tableau([
            {
                "ID": r["id"],
                "Activité": r.get("nom_activite") or "",
                "Risque": r.get("nom") or "",
                "Probabilité (%)": round(
                    min(
                        100,
                        float(r.get("probabilite") or 0)
                        * (
                            100
                            if float(r.get("probabilite") or 0) <= 1
                            else 1
                        )
                    ),
                    1
                ),
                "Impact": r.get("impact", 1),
                "Statut": r.get("statut", ""),
                "Prévention": r.get("mesure_prevention", "")
            }
            for r in risques_activites
        ])

        if risques_activites:

            st.subheader("Priorisation des risques")

            donnees_risques = []

            for r in risques_activites:

                p = float(
                    r.get("probabilite") or 0
                )

                if p > 1:
                    p = p / 100

                impact_r = float(
                    r.get("impact") or 1
                )

                score, niveau = evaluer_risque(
                    p,
                    impact_r
                )

                donnees_risques.append({
                    "Activité": r.get("nom_activite") or "",
                    "Risque": r.get("nom") or "",
                    "Score de risque": round(score, 1),
                    "Niveau": niveau
                })

            donnees_risques.sort(
                key=lambda x: x["Score de risque"],
                reverse=True
            )

            afficher_tableau(
                donnees_risques
            )

            st.info(
                "Le score est un indicateur de priorité : "
                "probabilité × impact × 100. "
                "Il ne constitue pas une probabilité de perte financière. "
                "Les risques d'activité ne sont pas ajoutés automatiquement "
                "à la simulation globale, afin d'éviter les doubles comptes."
            )

            ids = [
                r["id"] for r in risques_activites
            ]

            id_supp = st.selectbox(
                "Sélectionner un risque d'activité à supprimer",
                ids,
                key="risque_activite_supp"
            )

            confirmation = st.checkbox(
                "Confirmer cette suppression",
                key="confirmation_risque_activite"
            )

            if st.button(
                "Supprimer ce risque d'activité",
                disabled=not confirmation
            ):

                supprimer_risque_db(
                    id_supp
                )

                st.success(
                    "Risque supprimé."
                )

                st.rerun()


# ============================================================
# 9. DIAGRAMME DE GANTT — NOUVELLE FONCTIONNALITÉ C
# ============================================================

elif page == "Diagramme de Gantt":

    st.header("📅 Planification des activités — Diagramme de Gantt")

    st.write(
        "Le diagramme de Gantt représente les activités du chantier "
        "sur une période donnée. Il permet de comparer les dates "
        "prévues, les durées, les dépendances et l'avancement."
    )

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(
            chantier_id
        )

        activites = lire_activites(
            chantier_id
        )

        st.subheader("Ajouter une activité")

        with st.form("form_nouvelle_activite"):

            nom = st.text_input(
                "Nom de l'activité",
                placeholder="Ex. : Terrassement"
            )

            description = st.text_area(
                "Description"
            )

            date_debut = st.date_input(
                "Date de début prévue",
                value=date.today()
            )

            duree_prevue = st.number_input(
                "Durée prévue (jours)",
                min_value=1,
                max_value=3650,
                value=7
            )

            st.markdown("#### Informations réelles")

            debut_reel_actif = st.checkbox(
                "L'activité a-t-elle déjà commencé ?",
                key="debut_reel_actif"
            )

            if debut_reel_actif:

                date_debut_reelle = st.date_input(
                    "Date réelle de début",
                    value=date.today()
                )

                duree_reelle = st.number_input(
                    "Durée réelle ou durée estimée finale (jours)",
                    min_value=0.0,
                    value=0.0,
                    step=1.0
                )

                duree_reelle = (
                    duree_reelle
                    if duree_reelle > 0
                    else None
                )

            else:
                date_debut_reelle = None
                duree_reelle = None

            avancement = st.slider(
                "Avancement de l'activité (%)",
                0,
                100,
                0
            )

            statut = st.selectbox(
                "Statut de l'activité",
                [
                    "À faire",
                    "En cours",
                    "Terminé",
                    "En retard",
                    "Suspendu"
                ]
            )

            cout_prevu = st.number_input(
                "Coût prévu de l'activité (FCFA)",
                min_value=0.0,
                value=0.0,
                step=10000.0
            )

            dependance_id = None

            if activites:

                activites_possibles = {
                    "Aucune dépendance": None
                }

                for a in activites:

                    activites_possibles[
                        f"{a['nom']} — ID {a['id']}"
                    ] = a["id"]

                dependance_choisie = st.selectbox(
                    "Activité qui doit être terminée avant celle-ci",
                    list(activites_possibles.keys())
                )

                dependance_id = activites_possibles[
                    dependance_choisie
                ]

            observations = st.text_area(
                "Observations"
            )

            enregistrer_activite = st.form_submit_button(
                "Ajouter l'activité"
            )

        if enregistrer_activite:

            if not nom.strip():

                st.error(
                    "Le nom de l'activité est obligatoire."
                )

            else:

                if debut_reel_actif:
                    debut_reel = date_debut_reelle
                else:
                    debut_reel = None

                ajouter_activite_db(
                    chantier_id,
                    nom.strip(),
                    description,
                    date_debut,
                    duree_prevue,
                    debut_reel,
                    duree_reelle,
                    avancement,
                    statut,
                    dependance_id,
                    cout_prevu,
                    observations
                )

                st.success(
                    "Activité ajoutée au planning."
                )

                st.rerun()

        st.divider()

        activites = lire_activites(
            chantier_id
        )

        st.subheader("Diagramme de Gantt")

        if not activites:

            st.info(
                "Aucune activité planifiée. "
                "Ajoute des activités pour construire le diagramme."
            )

        else:

            html_gantt = generer_gantt_html(
                activites
            )

            st.components.v1.html(
                html_gantt,
                height=max(
                    250,
                    100 + len(activites) * 55
                ),
                scrolling=True
            )

            st.caption(
                "Les barres représentent les durées prévues. "
                "Les couleurs correspondent aux statuts des activités."
            )

            st.divider()

            st.subheader("Planning détaillé")

            lignes = []

            for a in activites:

                debut_prevu = a.get(
                    "date_debut_prevue"
                ) or ""

                try:

                    d = date.fromisoformat(
                        debut_prevu
                    )

                    duree = max(
                        1,
                        int(float(a.get("duree_prevue") or 1))
                    )

                    fin_prevue = (
                        d + timedelta(days=duree)
                    ).isoformat()

                except (ValueError, TypeError):

                    fin_prevue = ""

                lignes.append({
                    "ID": a["id"],
                    "Activité": a.get("nom", ""),
                    "Début prévu": debut_prevu,
                    "Fin prévue": fin_prevue,
                    "Durée prévue (jours)": a.get("duree_prevue", 0),
                    "Début réel": a.get("date_debut_reelle") or "",
                    "Durée réelle": a.get("duree_reelle") or "",
                    "Avancement (%)": a.get("avancement", 0),
                    "Statut": a.get("statut", ""),
                    "Dépendance": a.get("nom_dependance") or "Aucune",
                    "Coût prévu": fcfa(a.get("cout_prevu", 0))
                })

            afficher_tableau(
                lignes
            )

            st.divider()

            st.subheader("Modifier une activité")

            ids_activites = {
                f"{a['nom']} — ID {a['id']}": a["id"]
                for a in activites
            }

            choix_activite = st.selectbox(
                "Activité à modifier",
                list(ids_activites.keys()),
                key="activite_a_modifier"
            )

            activite_id = ids_activites[
                choix_activite
            ]

            activite = next(
                a for a in activites
                if a["id"] == activite_id
            )

            with st.form("form_modifier_activite"):

                nom_mod = st.text_input(
                    "Nom",
                    value=activite.get("nom") or "",
                    key="nom_activite_mod"
                )

                description_mod = st.text_area(
                    "Description",
                    value=activite.get("description") or "",
                    key="description_activite_mod"
                )

                try:
                    date_mod_initiale = date.fromisoformat(
                        activite.get("date_debut_prevue")
                        or date.today().isoformat()
                    )
                except ValueError:
                    date_mod_initiale = date.today()

                debut_mod = st.date_input(
                    "Début prévu",
                    value=date_mod_initiale,
                    key="debut_activite_mod"
                )

                duree_mod = st.number_input(
                    "Durée prévue (jours)",
                    min_value=1,
                    max_value=3650,
                    value=max(
                        1,
                        int(float(activite.get("duree_prevue") or 1))
                    ),
                    key="duree_activite_mod"
                )

                debut_reel_mod_actif = st.checkbox(
                    "Renseigner la date réelle de début",
                    value=bool(activite.get("date_debut_reelle")),
                    key="debut_reel_mod_actif"
                )

                if debut_reel_mod_actif:

                    try:
                        valeur_date_reelle = date.fromisoformat(
                            activite.get("date_debut_reelle")
                            or date.today().isoformat()
                        )
                    except ValueError:
                        valeur_date_reelle = date.today()

                    debut_reel_mod = st.date_input(
                        "Date réelle de début",
                        value=valeur_date_reelle,
                        key="debut_reel_mod"
                    )

                    duree_reelle_mod = st.number_input(
                        "Durée réelle ou estimée finale",
                        min_value=0.0,
                        value=float(
                            activite.get("duree_reelle") or 0
                        ),
                        step=1.0,
                        key="duree_reelle_mod"
                    )

                    duree_reelle_mod = (
                        duree_reelle_mod
                        if duree_reelle_mod > 0
                        else None
                    )

                else:

                    debut_reel_mod = None
                    duree_reelle_mod = None

                avancement_mod = st.slider(
                    "Avancement (%)",
                    0,
                    100,
                    int(
                        max(
                            0,
                            min(
                                100,
                                float(activite.get("avancement") or 0)
                            )
                        )
                    ),
                    key="avancement_activite_mod"
                )

                statut_mod = st.selectbox(
                    "Statut",
                    [
                        "À faire",
                        "En cours",
                        "Terminé",
                        "En retard",
                        "Suspendu"
                    ],
                    index=[
                        "À faire",
                        "En cours",
                        "Terminé",
                        "En retard",
                        "Suspendu"
                    ].index(
                        activite.get("statut")
                        if activite.get("statut") in [
                            "À faire",
                            "En cours",
                            "Terminé",
                            "En retard",
                            "Suspendu"
                        ]
                        else "À faire"
                    ),
                    key="statut_activite_mod"
                )

                cout_mod = st.number_input(
                    "Coût prévu (FCFA)",
                    min_value=0.0,
                    value=float(
                        activite.get("cout_prevu") or 0
                    ),
                    step=10000.0,
                    key="cout_activite_mod"
                )

                activites_possibles_mod = {
                    "Aucune dépendance": None
                }

                for a in activites:

                    if a["id"] != activite_id:

                        activites_possibles_mod[
                            f"{a['nom']} — ID {a['id']}"
                        ] = a["id"]

                dependance_actuelle = activite.get(
                    "dependance_id"
                )

                cle_dependance = "Aucune dépendance"

                for cle, valeur in activites_possibles_mod.items():

                    if valeur == dependance_actuelle:
                        cle_dependance = cle
                        break

                dependance_mod_choisie = st.selectbox(
                    "Dépendance",
                    list(activites_possibles_mod.keys()),
                    index=list(
                        activites_possibles_mod.keys()
                    ).index(cle_dependance),
                    key="dependance_activite_mod"
                )

                observations_mod = st.text_area(
                    "Observations",
                    value=activite.get("observations") or "",
                    key="observations_activite_mod"
                )

                modifier_activite = st.form_submit_button(
                    "Enregistrer les modifications"
                )

            if modifier_activite:

                if not nom_mod.strip():

                    st.error(
                        "Le nom de l'activité est obligatoire."
                    )

                elif (
                    activites_possibles_mod[
                        dependance_mod_choisie
                    ] == activite_id
                ):

                    st.error(
                        "Une activité ne peut pas dépendre d'elle-même."
                    )

                else:

                    modifier_activite_db(
                        activite_id,
                        nom_mod.strip(),
                        description_mod,
                        debut_mod,
                        duree_mod,
                        debut_reel_mod,
                        duree_reelle_mod,
                        avancement_mod,
                        statut_mod,
                        activites_possibles_mod[
                            dependance_mod_choisie
                        ],
                        cout_mod,
                        observations_mod
                    )

                    st.success(
                        "Activité mise à jour."
                    )

                    st.rerun()

            st.divider()

            st.subheader("Supprimer une activité")

            activite_supp = st.selectbox(
                "Activité à supprimer",
                list(ids_activites.keys()),
                key="activite_a_supprimer"
            )

            confirmation_supp_activite = st.checkbox(
                "Je confirme la suppression de cette activité",
                key="confirmation_supp_activite"
            )

            if st.button(
                "Supprimer l'activité",
                disabled=not confirmation_supp_activite
            ):

                supprimer_activite_db(
                    ids_activites[activite_supp]
                )

                st.success(
                    "Activité supprimée."
                )

                st.rerun()


# ============================================================
# 10. GESTION DES INCIDENTS
# ============================================================

elif page == "Gestion des incidents":

    st.header("🚧 Gestion des incidents")

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        st.subheader("Déclarer un incident")

        with st.form("form_incident"):

            titre = st.text_input(
                "Titre de l'incident"
            )

            description = st.text_area(
                "Description de l'incident"
            )

            gravite = st.selectbox(
                "Gravité",
                [
                    "Faible",
                    "Moyenne",
                    "Élevée",
                    "Critique"
                ]
            )

            cout_estime = st.number_input(
                "Coût estimé de l'incident (FCFA)",
                min_value=0.0,
                value=0.0,
                step=10000.0
            )

            jours_retard = st.number_input(
                "Retard estimé (jours)",
                min_value=0.0,
                value=0.0,
                step=1.0
            )

            statut = st.selectbox(
                "Statut",
                [
                    "Ouvert",
                    "En cours",
                    "Résolu",
                    "Clôturé"
                ]
            )

            enregistrer_incident = st.form_submit_button(
                "Enregistrer l'incident"
            )

        if enregistrer_incident:

            if not titre.strip():

                st.error(
                    "Le titre de l'incident est obligatoire."
                )

            else:

                ajouter_incident_db(
                    chantier_id,
                    titre.strip(),
                    description,
                    gravite,
                    cout_estime,
                    jours_retard,
                    statut
                )

                st.success(
                    "Incident enregistré."
                )

                st.rerun()

        st.divider()

        st.subheader("Incidents enregistrés")

        incidents = lire_incidents(
            chantier_id
        )

        afficher_tableau([
            {
                "ID": i["id"],
                "Titre": i.get("titre", ""),
                "Description": i.get("description", ""),
                "Gravité": i.get("gravite", ""),
                "Coût estimé": fcfa(i.get("cout_estime", 0)),
                "Retard (jours)": i.get("jours_retard", 0),
                "Date": i.get("date_incident", ""),
                "Statut": i.get("statut", "")
            }
            for i in incidents
        ])

        if incidents:

            incident_ids = [
                i["id"] for i in incidents
            ]

            incident_supp = st.selectbox(
                "Incident à supprimer",
                incident_ids,
                key="incident_supp"
            )

            confirmation_incident = st.checkbox(
                "Confirmer la suppression de l'incident",
                key="confirmation_incident"
            )

            if st.button(
                "Supprimer l'incident",
                disabled=not confirmation_incident
            ):

                supprimer_incident_db(
                    incident_supp
                )

                st.success(
                    "Incident supprimé."
                )

                st.rerun()


# ============================================================
# 11. ANALYSE BUDGÉTAIRE
# ============================================================

elif page == "Analyse budgétaire":

    st.header("💹 Analyse budgétaire")

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(
            chantier_id
        )

        budget = float(
            chantier.get("budget") or 0
        )

        depenses = total_depenses(
            chantier_id
        )

        reste = budget - depenses

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Budget prévu",
            fcfa(budget)
        )

        c2.metric(
            "Dépenses",
            fcfa(depenses)
        )

        c3.metric(
            "Écart budgétaire",
            fcfa(reste)
        )

        if budget > 0:

            taux = depenses / budget * 100

            st.write(
                f"Consommation du budget : {taux:.2f} %"
            )

            st.progress(
                max(0.0, min(1.0, taux / 100))
            )

            if depenses > budget:

                st.error(
                    "Le budget prévu est dépassé."
                )

            elif taux >= 80:

                st.warning(
                    "Une grande partie du budget est déjà consommée."
                )

            else:

                st.success(
                    "Les dépenses enregistrées restent "
                    "inférieures au budget prévu."
                )

        depenses_lues = lire_depenses(
            chantier_id
        )

        if depenses_lues:

            st.subheader("Répartition des dépenses")

            try:
                import pandas as pd
                import matplotlib.pyplot as plt

                df = pd.DataFrame(
                    depenses_lues
                )

                df["montant"] = pd.to_numeric(
                    df["montant"],
                    errors="coerce"
                ).fillna(0)

                repartition = df.groupby(
                    "categorie"
                )["montant"].sum()

                fig, ax = plt.subplots()

                repartition.plot(
                    kind="pie",
                    autopct="%1.1f%%",
                    ax=ax
                )

                ax.set_ylabel("")
                ax.set_title(
                    "Répartition des dépenses par catégorie"
                )

                plt.tight_layout()

                st.pyplot(fig)
                plt.close(fig)

            except ImportError:
                st.info(
                    "Le graphique nécessite pandas et matplotlib."
                )

            st.subheader("Historique financier")

            afficher_tableau([
                {
                    "Date": d.get("date_depense", ""),
                    "Catégorie": d.get("categorie", ""),
                    "Montant": fcfa(d.get("montant", 0)),
                    "Description": d.get("description", "")
                }
                for d in depenses_lues
            ])


# ============================================================
# 12. ANALYSE PROBABILISTE
# ============================================================

elif page == "Analyse probabiliste":

    st.header("📉 Analyse probabiliste du chantier")

    st.write(
        "Cette analyse estime le risque de dépassement du budget "
        "et de la durée prévue à partir d'hypothèses de coût "
        "et de durée."
    )

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(
            chantier_id
        )

        budget = float(
            chantier.get("budget") or 0
        )

        duree_prevue = float(
            chantier.get("duree") or 0
        )

        depenses = total_depenses(
            chantier_id
        )

        avancement = dernier_avancement(
            chantier_id
        )

        st.subheader("Données de départ")

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Budget prévu",
            fcfa(budget)
        )

        c2.metric(
            "Durée prévue",
            f"{duree_prevue:.0f} jours"
        )

        c3.metric(
            "Avancement",
            f"{avancement:.1f} %"
        )

        incertitude_cout = st.slider(
            "Incertitude relative sur le coût (%)",
            1,
            60,
            15,
            key="incertitude_cout_simple"
        ) / 100

        incertitude_delai = st.slider(
            "Incertitude relative sur la durée (%)",
            1,
            60,
            20,
            key="incertitude_delai_simple"
        ) / 100

        retard_incidents = sum(
            float(i.get("jours_retard") or 0)
            for i in lire_incidents(chantier_id)
            if i.get("statut") not in [
                "Résolu",
                "Clôturé"
            ]
        )

        if st.button(
            "Lancer l'analyse probabiliste",
            key="lancer_analyse_simple"
        ):

            resultat = simulation_monte_carlo(
                budget,
                duree_prevue,
                depenses,
                avancement,
                iterations=5000,
                incertitude_cout=incertitude_cout,
                incertitude_delai=incertitude_delai,
                retard_incidents=retard_incidents
            )

            if resultat is None:

                st.error(
                    "Le budget et la durée prévus doivent "
                    "être supérieurs à zéro."
                )

            else:

                st.session_state[
                    "resultat_analyse_simple"
                ] = resultat

        resultat = st.session_state.get(
            "resultat_analyse_simple"
        )

        if resultat:

            st.divider()

            st.subheader("Résultats de la simulation")

            c1, c2 = st.columns(2)

            c1.metric(
                "Coût moyen estimé",
                fcfa(resultat["cout_moyen"])
            )

            c2.metric(
                "Durée moyenne estimée",
                f"{resultat['duree_moyenne']:.1f} jours"
            )

            c1, c2 = st.columns(2)

            c1.metric(
                "Probabilité de dépassement du budget",
                f"{resultat['prob_cout']:.1f} %"
            )

            c2.metric(
                "Probabilité de dépassement du délai",
                f"{resultat['prob_delai']:.1f} %"
            )

            st.subheader("Scénarios de coûts")

            afficher_tableau([
                {
                    "Indicateur": "Médiane",
                    "Coût estimé": fcfa(resultat["cout_mediane"])
                },
                {
                    "Indicateur": "80e percentile",
                    "Coût estimé": fcfa(resultat["cout_p80"])
                },
                {
                    "Indicateur": "90e percentile",
                    "Coût estimé": fcfa(resultat["cout_p90"])
                },
                {
                    "Indicateur": "95e percentile",
                    "Coût estimé": fcfa(resultat["cout_p95"])
                }
            ])

            st.subheader("Scénarios de durée")

            afficher_tableau([
                {
                    "Indicateur": "Médiane",
                    "Durée estimée": f"{resultat['duree_mediane']:.1f} jours"
                },
                {
                    "Indicateur": "80e percentile",
                    "Durée estimée": f"{resultat['duree_p80']:.1f} jours"
                },
                {
                    "Indicateur": "90e percentile",
                    "Durée estimée": f"{resultat['duree_p90']:.1f} jours"
                },
                {
                    "Indicateur": "95e percentile",
                    "Durée estimée": f"{resultat['duree_p95']:.1f} jours"
                }
            ])

            st.warning(
                "Interprétation : ces résultats dépendent des hypothèses "
                "de simulation. Le coût central est extrapolé à partir "
                "des dépenses et de l'avancement lorsqu'ils sont disponibles. "
                "Ce n'est pas une garantie du coût final."
            )


# ============================================================
# 13. ANALYSE PROBABILISTE AVANCÉE — NOUVELLE FONCTIONNALITÉ A
# ============================================================

elif page == "Analyse probabiliste avancée":

    st.header("🧮 Analyse probabiliste avancée")

    st.write(
        "Compare plusieurs scénarios de coûts et de durées "
        "avec une distribution triangulaire ou normale."
    )

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(
            chantier_id
        )

        budget = float(
            chantier.get("budget") or 0
        )

        duree_prevue = float(
            chantier.get("duree") or 0
        )

        st.subheader("Paramètres du chantier")

        c1, c2 = st.columns(2)

        with c1:

            budget_reference = st.number_input(
                "Budget de référence (FCFA)",
                min_value=1.0,
                value=max(1.0, budget),
                step=100000.0
            )

        with c2:

            duree_reference = st.number_input(
                "Durée de référence (jours)",
                min_value=1.0,
                value=max(1.0, duree_prevue),
                step=1.0
            )

        st.divider()

        st.subheader("Distribution statistique")

        distribution = st.radio(
            "Choisir une distribution",
            [
                "Triangulaire",
                "Normale"
            ],
            horizontal=True
        )

        st.caption(
            "Triangulaire : minimum, valeur la plus probable, maximum. "
            "Normale : moyenne et écart-type calculé à partir "
            "de l'intervalle fourni."
        )

        st.subheader("Hypothèses de coût")

        col1, col2, col3 = st.columns(3)

        with col1:

            cout_min = st.number_input(
                "Coût minimum (FCFA)",
                min_value=0.0,
                value=max(
                    0.0,
                    budget_reference * 0.80
                ),
                step=100000.0
            )

        with col2:

            cout_central = st.number_input(
                "Coût central (FCFA)",
                min_value=0.0,
                value=budget_reference,
                step=100000.0
            )

        with col3:

            cout_max = st.number_input(
                "Coût maximum (FCFA)",
                min_value=0.0,
                value=budget_reference * 1.40,
                step=100000.0
            )

        st.subheader("Hypothèses de durée")

        col1, col2, col3 = st.columns(3)

        with col1:

            duree_min = st.number_input(
                "Durée minimale (jours)",
                min_value=0.0,
                value=max(
                    0.0,
                    duree_reference * 0.80
                ),
                step=1.0
            )

        with col2:

            duree_centrale = st.number_input(
                "Durée centrale (jours)",
                min_value=0.0,
                value=duree_reference,
                step=1.0
            )

        with col3:

            duree_max = st.number_input(
                "Durée maximale (jours)",
                min_value=0.0,
                value=duree_reference * 1.50,
                step=1.0
            )

        iterations = st.select_slider(
            "Nombre de simulations",
            options=[
                1000,
                2500,
                5000,
                10000,
                25000,
                50000
            ],
            value=10000
        )

        lancer = st.button(
            "Lancer la simulation avancée",
            type="primary"
        )

        if lancer:

            erreurs = []

            if budget_reference <= 0:
                erreurs.append(
                    "Le budget de référence doit être positif."
                )

            if duree_reference <= 0:
                erreurs.append(
                    "La durée de référence doit être positive."
                )

            if not (
                0 <= cout_min
                <= cout_central
                <= cout_max
            ):
                erreurs.append(
                    "Les coûts doivent respecter : "
                    "minimum ≤ central ≤ maximum."
                )

            if not (
                0 <= duree_min
                <= duree_centrale
                <= duree_max
            ):
                erreurs.append(
                    "Les durées doivent respecter : "
                    "minimum ≤ centrale ≤ maximum."
                )

            if erreurs:

                for erreur in erreurs:
                    st.error(erreur)

            else:

                resultat = simulation_probabiliste_avancee(
                    budget_reference,
                    duree_reference,
                    cout_min,
                    cout_central,
                    cout_max,
                    duree_min,
                    duree_centrale,
                    duree_max,
                    distribution,
                    iterations
                )

                st.session_state[
                    "resultat_probabiliste_avance"
                ] = resultat

                st.session_state[
                    "parametres_probabilistes_avances"
                ] = {
                    "budget": budget_reference,
                    "duree": duree_reference,
                    "distribution": distribution
                }

        resultat = st.session_state.get(
            "resultat_probabiliste_avance"
        )

        if resultat:

            st.divider()

            st.subheader("Résultats statistiques")

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Coût moyen",
                fcfa(resultat["cout_moyen"])
            )

            c2.metric(
                "Durée moyenne",
                f"{resultat['duree_moyenne']:.1f} jours"
            )

            c3.metric(
                "Nombre de simulations",
                resultat["iterations"]
            )

            c1, c2 = st.columns(2)

            c1.metric(
                "Risque de dépassement du budget",
                f"{resultat['prob_cout']:.2f} %"
            )

            c2.metric(
                "Risque de dépassement du délai",
                f"{resultat['prob_delai']:.2f} %"
            )

            st.subheader("Percentiles des coûts")

            afficher_tableau([
                {
                    "Percentile": "P50",
                    "Interprétation": "50 % des simulations sont en dessous",
                    "Coût": fcfa(resultat["cout_p50"])
                },
                {
                    "Percentile": "P80",
                    "Interprétation": "80 % des simulations sont en dessous",
                    "Coût": fcfa(resultat["cout_p80"])
                },
                {
                    "Percentile": "P90",
                    "Interprétation": "90 % des simulations sont en dessous",
                    "Coût": fcfa(resultat["cout_p90"])
                },
                {
                    "Percentile": "P95",
                    "Interprétation": "95 % des simulations sont en dessous",
                    "Coût": fcfa(resultat["cout_p95"])
                }
            ])

            st.subheader("Percentiles des durées")

            afficher_tableau([
                {
                    "Percentile": "P50",
                    "Durée (jours)": round(
                        resultat["duree_p50"], 1
                    )
                },
                {
                    "Percentile": "P80",
                    "Durée (jours)": round(
                        resultat["duree_p80"], 1
                    )
                },
                {
                    "Percentile": "P90",
                    "Durée (jours)": round(
                        resultat["duree_p90"], 1
                    )
                },
                {
                    "Percentile": "P95",
                    "Durée (jours)": round(
                        resultat["duree_p95"], 1
                    )
                }
            ])

            st.divider()

            st.subheader("Distribution des coûts simulés")

            try:

                import matplotlib.pyplot as plt

                fig, ax = plt.subplots()

                ax.hist(
                    resultat["couts"],
                    bins=40
                )

                ax.axvline(
                    budget_reference,
                    linestyle="--",
                    label="Budget de référence"
                )

                ax.set_title(
                    "Distribution des coûts simulés"
                )

                ax.set_xlabel("Coût en FCFA")
                ax.set_ylabel("Fréquence")

                ax.legend()

                plt.tight_layout()

                st.pyplot(fig)
                plt.close(fig)

                fig, ax = plt.subplots()

                ax.hist(
                    resultat["durees"],
                    bins=40
                )

                ax.axvline(
                    duree_reference,
                    linestyle="--",
                    label="Durée de référence"
                )

                ax.set_title(
                    "Distribution des durées simulées"
                )

                ax.set_xlabel("Durée en jours")
                ax.set_ylabel("Fréquence")

                ax.legend()

                plt.tight_layout()

                st.pyplot(fig)
                plt.close(fig)

            except ImportError:

                st.info(
                    "Les histogrammes nécessitent matplotlib."
                )

            st.info(
                "Les probabilités sont calculées à partir des "
                "tirages simulés. Les hypothèses de coût et de durée "
                "doivent être justifiées par des données de chantier, "
                "des devis ou l'expérience des ingénieurs."
            )


# ============================================================
# 14. SIMULATION MONTE-CARLO
# ============================================================

elif page == "Simulation Monte-Carlo":

    st.header("🎲 Simulation de Monte-Carlo")

    st.write(
        "Cette simulation génère de nombreux scénarios possibles "
        "pour estimer la dispersion des coûts et des durées."
    )

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(
            chantier_id
        )

        budget = float(
            chantier.get("budget") or 0
        )

        duree_prevue = float(
            chantier.get("duree") or 0
        )

        depenses = total_depenses(
            chantier_id
        )

        avancement = dernier_avancement(
            chantier_id
        )

        incidents = lire_incidents(
            chantier_id
        )

        retard_incidents = sum(
            float(i.get("jours_retard") or 0)
            for i in incidents
            if i.get("statut") not in [
                "Résolu",
                "Clôturé"
            ]
        )

        c1, c2 = st.columns(2)

        c1.metric(
            "Budget prévu",
            fcfa(budget)
        )

        c2.metric(
            "Durée prévue",
            f"{duree_prevue:.0f} jours"
        )

        st.metric(
            "Avancement enregistré",
            f"{avancement:.1f} %"
        )

        st.metric(
            "Retards associés aux incidents ouverts",
            f"{retard_incidents:.0f} jours"
        )

        st.divider()

        st.subheader("Paramètres de simulation")

        iterations = st.select_slider(
            "Nombre d'itérations",
            options=[
                1000,
                2500,
                5000,
                10000,
                25000,
                50000
            ],
            value=5000,
            key="iterations_monte_carlo"
        )

        incertitude_cout = st.slider(
            "Incertitude sur le coût (%)",
            1,
            60,
            15,
            key="mc_incertitude_cout"
        ) / 100

        incertitude_delai = st.slider(
            "Incertitude sur la durée (%)",
            1,
            60,
            20,
            key="mc_incertitude_delai"
        ) / 100

        if st.button(
            "Exécuter Monte-Carlo",
            type="primary"
        ):

            resultat = simulation_monte_carlo(
                budget,
                duree_prevue,
                depenses,
                avancement,
                iterations=iterations,
                incertitude_cout=incertitude_cout,
                incertitude_delai=incertitude_delai,
                retard_incidents=retard_incidents
            )

            if resultat is None:

                st.error(
                    "Vérifie le budget et la durée du chantier."
                )

            else:

                st.session_state[
                    "resultat_monte_carlo"
                ] = resultat

        resultat = st.session_state.get(
            "resultat_monte_carlo"
        )

        if resultat:

            st.divider()

            st.subheader("Résultats")

            c1, c2 = st.columns(2)

            c1.metric(
                "Coût moyen estimé",
                fcfa(resultat["cout_moyen"])
            )

            c2.metric(
                "Durée moyenne estimée",
                f"{resultat['duree_moyenne']:.1f} jours"
            )

            c1, c2 = st.columns(2)

            c1.metric(
                "Probabilité de dépassement du budget",
                f"{resultat['prob_cout']:.2f} %"
            )

            c2.metric(
                "Probabilité de dépassement du délai",
                f"{resultat['prob_delai']:.2f} %"
            )

            st.subheader("Scénarios financiers")

            afficher_tableau([
                {
                    "Scénario": "Médian",
                    "Coût": fcfa(resultat["cout_mediane"])
                },
                {
                    "Scénario": "Prudent P80",
                    "Coût": fcfa(resultat["cout_p80"])
                },
                {
                    "Scénario": "Prudent P90",
                    "Coût": fcfa(resultat["cout_p90"])
                },
                {
                    "Scénario": "Très prudent P95",
                    "Coût": fcfa(resultat["cout_p95"])
                }
            ])

            try:

                import matplotlib.pyplot as plt

                fig, ax = plt.subplots()

                ax.hist(
                    resultat["couts"],
                    bins=40
                )

                ax.set_title(
                    "Distribution des coûts"
                )

                ax.set_xlabel("Coût en FCFA")
                ax.set_ylabel("Nombre de simulations")

                plt.tight_layout()

                st.pyplot(fig)
                plt.close(fig)

                fig, ax = plt.subplots()

                ax.hist(
                    resultat["durees"],
                    bins=40
                )

                ax.set_title(
                    "Distribution des durées"
                )

                ax.set_xlabel("Durée en jours")
                ax.set_ylabel("Nombre de simulations")

                plt.tight_layout()

                st.pyplot(fig)
                plt.close(fig)

            except ImportError:

                st.info(
                    "Installe matplotlib uniquement si tu souhaites "
                    "afficher les histogrammes."
                )

            st.warning(
                "La simulation classique utilise une estimation centrale "
                "basée sur le budget, les dépenses et l'avancement. "
                "Les résultats sont indicatifs et dépendent des hypothèses."
            )


# ============================================================
# 15. PRÉVISIONS SUR CINQ ANS
# ============================================================

elif page == "Prévisions sur 5 ans":

    st.header("📆 Prévisions financières sur cinq ans")

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(
            chantier_id
        )

        budget = float(
            chantier.get("budget") or 0
        )

        depenses = total_depenses(
            chantier_id
        )

        st.metric(
            "Budget actuel",
            fcfa(budget)
        )

        st.metric(
            "Dépenses actuelles",
            fcfa(depenses)
        )

        st.divider()

        inflation = st.number_input(
            "Hypothèse d'inflation annuelle (%)",
            min_value=0.0,
            max_value=100.0,
            value=3.0,
            step=0.5
        )

        croissance_risque = st.number_input(
            "Réserve annuelle pour risques (%)",
            min_value=0.0,
            max_value=100.0,
            value=10.0,
            step=1.0
        )

        annees = st.selectbox(
            "Horizon de prévision",
            [1, 2, 3, 4, 5],
            index=4
        )

        iterations = st.selectbox(
            "Nombre de simulations par année",
            [1000, 2500, 5000, 10000],
            index=2
        )

        if st.button(
            "Calculer les prévisions"
        ):

            previsions, simulations = (
                simulation_financiere_cinq_ans(
                    budget,
                    depenses,
                    inflation,
                    croissance_risque,
                    annees,
                    iterations
                )
            )

            st.session_state[
                "previsions_cinq_ans"
            ] = previsions

            st.session_state[
                "simulations_cinq_ans"
            ] = simulations

        previsions = st.session_state.get(
            "previsions_cinq_ans"
        )

        simulations = st.session_state.get(
            "simulations_cinq_ans"
        )

        if previsions and simulations:

            st.subheader("Prévisions déterministes")

            afficher_tableau([
                {
                    "Année": r["Année"],
                    "Coût estimé": fcfa(r["Coût estimé"]),
                    "Réserve risques": fcfa(r["Réserve risques"]),
                    "Coût total": fcfa(r["Coût total estimé"])
                }
                for r in previsions
            ])

            st.subheader("Résultats des simulations")

            afficher_tableau([
                {
                    "Année": r["Année"],
                    "Coût moyen simulé": fcfa(
                        r["Coût moyen simulé"]
                    ),
                    "Médiane": fcfa(
                        r["Médiane"]
                    ),
                    "P90": fcfa(
                        r["P90"]
                    ),
                    "P95": fcfa(
                        r["P95"]
                    )
                }
                for r in simulations
            ])

            st.info(
                "Ces prévisions constituent un scénario mathématique "
                "simplifié. Elles ne remplacent pas un modèle financier "
                "calibré sur des données historiques."
            )


# ============================================================
# 16. RAPPORTS PDF ET EXCEL
# ============================================================

elif page == "Rapports PDF et Excel":

    st.header("📄 Rapports PDF et Excel")

    st.write(
        "Génère un rapport récapitulatif du chantier, "
        "un registre des dépenses, des risques, des incidents "
        "ou des activités planifiées."
    )

    chantier_id = choisir_chantier()

    if chantier_id is not None:

        chantier = obtenir_chantier(
            chantier_id
        )

        st.subheader(
            f"Rapports du chantier : {chantier['nom']}"
        )

        rapport = creer_donnees_rapport(
            chantier_id
        )

        st.markdown("### Résumé du chantier")

        for cle, valeur in rapport.items():

            st.write(
                f"**{cle} :** {valeur}"
            )

        st.divider()

        st.subheader("Export PDF")

        contenu_pdf = {
            "Nom du chantier": chantier.get("nom", ""),
            "Lieu": chantier.get("lieu", ""),
            "Responsable": chantier.get("responsable", ""),
            "Date de démarrage": chantier.get("date_demarrage", ""),
            "Durée prévue": f"{chantier.get('duree', 0)} jours",
            "Budget prévu": fcfa(
                chantier.get("budget", 0)
            ),
            "Dépenses": fcfa(
                total_depenses(chantier_id)
            ),
            "Budget restant": fcfa(
                float(chantier.get("budget") or 0)
                - total_depenses(chantier_id)
            ),
            "Avancement": (
                f"{dernier_avancement(chantier_id):.1f} %"
            )
        }

        pdf = creer_pdf(
            f"Rapport CIVI-PREDICT — {chantier['nom']}",
            contenu_pdf
        )

        if pdf is None:

            st.warning(
                "La génération PDF nécessite ReportLab. "
                "Le reste de l'application demeure disponible."
            )

            st.code(
                "python -m pip install reportlab",
                language="powershell"
            )

        else:

            st.download_button(
                label="📥 Télécharger le rapport PDF",
                data=pdf,
                file_name=(
                    f"rapport_civi_predict_{chantier_id}.pdf"
                ),
                mime="application/pdf"
            )

        st.divider()

        st.subheader("Export Excel")

        type_export = st.selectbox(
            "Choisir les données à exporter",
            [
                "Résumé du chantier",
                "Dépenses",
                "Activités",
                "Risques",
                "Incidents",
                "Avancements"
            ]
        )

        if type_export == "Résumé du chantier":

            donnees_excel = [
                {
                    "Indicateur": cle,
                    "Valeur": valeur
                }
                for cle, valeur in rapport.items()
            ]

            nom_feuille = "Résumé"

        elif type_export == "Dépenses":

            depenses = lire_depenses(
                chantier_id
            )

            donnees_excel = [
                {
                    "ID": d["id"],
                    "Catégorie": d.get("categorie", ""),
                    "Montant FCFA": d.get("montant", 0),
                    "Description": d.get("description", ""),
                    "Date": d.get("date_depense", "")
                }
                for d in depenses
            ]

            nom_feuille = "Depenses"

        elif type_export == "Activités":

            activites = lire_activites(
                chantier_id
            )

            donnees_excel = [
                {
                    "ID": a["id"],
                    "Nom": a.get("nom", ""),
                    "Description": a.get("description", ""),
                    "Début prévu": a.get("date_debut_prevue", ""),
                    "Durée prévue": a.get("duree_prevue", 0),
                    "Début réel": a.get("date_debut_reelle") or "",
                    "Durée réelle": a.get("duree_reelle") or "",
                    "Avancement": a.get("avancement", 0),
                    "Statut": a.get("statut", ""),
                    "Dépendance": a.get("dependance_id") or "",
                    "Coût prévu": a.get("cout_prevu", 0)
                }
                for a in activites
            ]

            nom_feuille = "Activites"

        elif type_export == "Risques":

            risques = lire_risques(
                chantier_id
            )

            donnees_excel = [
                {
                    "ID": r["id"],
                    "Nom": r.get("nom", ""),
                    "Probabilité": r.get("probabilite", 0),
                    "Impact": r.get("impact", 0),
                    "Prévention": r.get("mesure_prevention", ""),
                    "Statut": r.get("statut", ""),
                    "Activité": r.get("nom_activite") or "Général"
                }
                for r in risques
            ]

            nom_feuille = "Risques"

        elif type_export == "Incidents":

            incidents = lire_incidents(
                chantier_id
            )

            donnees_excel = [
                {
                    "ID": i["id"],
                    "Titre": i.get("titre", ""),
                    "Description": i.get("description", ""),
                    "Gravité": i.get("gravite", ""),
                    "Coût estimé": i.get("cout_estime", 0),
                    "Retard en jours": i.get("jours_retard", 0),
                    "Date": i.get("date_incident", ""),
                    "Statut": i.get("statut", "")
                }
                for i in incidents
            ]

            nom_feuille = "Incidents"

        else:

            avancements = lire_avancements(
                chantier_id
            )

            donnees_excel = [
                {
                    "ID": a["id"],
                    "Pourcentage": a.get("pourcentage", 0),
                    "Description": a.get("description", ""),
                    "Date": a.get("date_avancement", "")
                }
                for a in avancements
            ]

            nom_feuille = "Avancements"

        excel = creer_excel(
            donnees_excel,
            nom_feuille
        )

        if excel is None:

            st.warning(
                "La génération Excel nécessite openpyxl."
            )

            st.code(
                "python -m pip install openpyxl",
                language="powershell"
            )

        else:

            st.download_button(
                label="📥 Télécharger le fichier Excel",
                data=excel,
                file_name=(
                    f"civi_predict_{nom_feuille.lower()}_"
                    f"{chantier_id}.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                )
            )

        st.divider()

        st.subheader("Données enregistrées")

        st.write(
            f"Nombre de dépenses : "
            f"{len(lire_depenses(chantier_id))}"
        )

        st.write(
            f"Nombre d'activités : "
            f"{len(lire_activites(chantier_id))}"
        )

        st.write(
            f"Nombre de risques : "
            f"{len(lire_risques(chantier_id))}"
        )

        st.write(
            f"Nombre d'incidents : "
            f"{len(lire_incidents(chantier_id))}"
        )

        st.write(
            f"Nombre de suivis d'avancement : "
            f"{len(lire_avancements(chantier_id))}"
        )


# ============================================================
# PIED DE PAGE
# ============================================================

st.divider()

st.caption(
    "CIVI-PREDICT — Gestion des chantiers, "
    "suivi budgétaire et analyse probabiliste des risques."
)

st.caption(
    "Les estimations probabilistes dépendent des données "
    "et des hypothèses renseignées. Elles doivent être "
    "interprétées comme des aides à la décision."
)

# ============================================================
# FIN DU CODE CIVI-PREDICT
# ============================================================             