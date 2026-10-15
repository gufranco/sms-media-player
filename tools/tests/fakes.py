from faker import Faker

SEED = 20261015


def seeded() -> Faker:
    fake = Faker()
    fake.seed_instance(SEED)
    return fake
