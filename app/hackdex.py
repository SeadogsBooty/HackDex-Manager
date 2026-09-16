class HackDexProvider:
    """
    All HackDex-specific functionality belongs here.

    Other parts of HackDex Manager should never depend directly
    on HackDex's website implementation or backend.
    """

    def search(self, title: str):
        raise NotImplementedError

    def get_hack(self, slug: str):
        raise NotImplementedError

    def get_current_version(self, slug: str):
        raise NotImplementedError

    def get_versions(self, slug: str):
        raise NotImplementedError

    def get_variants(self, slug: str):
        raise NotImplementedError
