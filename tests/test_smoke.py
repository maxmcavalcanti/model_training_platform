def test_packages_are_importable():
    import flows
    import ingestion

    assert ingestion is not None
    assert flows is not None
