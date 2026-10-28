from src.retrieval import neighbor_ids, proper_nouns, round_robin, select_diverse, with_neighbors


def hit(n, chapter):
    return {"chunk_id": f"c{n:05d}", "chapter": chapter}


def ids(hits):
    return [h["chunk_id"] for h in hits]


def test_proper_nouns():
    assert proper_nouns("Qual é a relação entre Lúthien e Elrond?") == ["Lúthien", "Elrond"]
    assert proper_nouns("Qual rei morreu na Nirnaeth Arnoediad?") == ["Nirnaeth Arnoediad"]
    assert proper_nouns("Fëanor guardou as joias onde?") == ["Fëanor"]
    assert proper_nouns("Quem criou os artífices de Ost-in-Edhil?") == ["Ost-in-Edhil"]
    assert proper_nouns("Quem fez isso?") == []


def test_select_diverse_caps_per_chapter_and_fills():
    hits = [hit(0, "A"), hit(1, "A"), hit(2, "A"), hit(3, "B"), hit(4, "A")]
    assert ids(select_diverse(hits, 3, max_per_chapter=2)) == ["c00000", "c00001", "c00003"]
    # sem capítulos suficientes, completa com os que sobraram, na ordem
    assert ids(select_diverse(hits[:3], 3, max_per_chapter=1)) == ["c00000", "c00001", "c00002"]


def test_round_robin():
    a = [hit(0, "A"), hit(1, "A"), hit(2, "A")]
    b = [hit(9, "C"), hit(0, "A"), hit(10, "C")]
    assert ids(round_robin([a, b], 4)) == ["c00000", "c00009", "c00001", "c00002"]
    assert ids(round_robin([a, []], 10)) == ["c00000", "c00001", "c00002"]


def test_neighbor_ids():
    assert neighbor_ids("c00421") == ["c00420", "c00422"]
    assert neighbor_ids("c00000") == ["c00001"]


def test_with_neighbors_in_book_order_same_chapter_only():
    hits = [hit(421, "ANEIS"), hit(300, "TURIN"), hit(50, "X")]
    neighbors = {"c00420": hit(420, "ANEIS"), "c00422": hit(422, "ANEIS"),
                 "c00299": hit(299, "OUTRO"), "c00301": hit(301, "TURIN")}
    out = with_neighbors(hits, neighbors, expand_top=2)
    # c00299 é de outro capítulo e fica de fora; o 3º trecho não é expandido
    assert ids(out) == ["c00420", "c00421", "c00422", "c00300", "c00301", "c00050"]
    # vizinho que já estava na lista não se repete
    assert ids(with_neighbors([hit(1, "A"), hit(2, "A")], {"c00000": hit(0, "A"), "c00002": hit(2, "A")}, 1)) == \
        ["c00000", "c00001", "c00002"]
