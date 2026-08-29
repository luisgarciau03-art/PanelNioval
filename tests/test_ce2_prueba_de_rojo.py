"""Test que falla A PROPOSITO para comprobar el criterio CE2 del Plan 0.

Un CI que solo se ha visto en verde no esta probado. La regla del entorno sobre
barridos aplica igual a los gates: hay que comprobar que encuentra un positivo
conocido, no solo que no se queja.

Este archivo vive en la rama `ci/prueba-de-rojo`, se usa para confirmar que el
check queda en ROJO, y NO se mergea a main. Su unico proposito es que exista una
corrida del workflow fallida a la que poder apuntar como evidencia.
"""


def test_este_test_falla_a_proposito_para_probar_el_gate():
    """Si este test pasa, el gate no esta ejecutando la suite de verdad."""
    assert 1 == 2, "fallo deliberado: CE2 del Plan 0 exige ver el check en rojo"
