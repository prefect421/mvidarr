import { orderBy } from 'lodash';
import React, { useCallback, useMemo } from 'react';
import { useSelector } from 'react-redux';
import Artist from 'Artist/Artist';
import Alert from 'Components/Alert';
import Icon from 'Components/Icon';
import Button from 'Components/Link/Button';
import ModalBody from 'Components/Modal/ModalBody';
import ModalContent from 'Components/Modal/ModalContent';
import ModalFooter from 'Components/Modal/ModalFooter';
import ModalHeader from 'Components/Modal/ModalHeader';
import { icons, kinds } from 'Helpers/Props';
import createAllArtistSelector from 'Store/Selectors/createAllArtistSelector';
import createAjaxRequest from 'Utilities/createAjaxRequest';
import translate from 'Utilities/String/translate';
import styles from './OrganizeArtistModalContent.css';

interface OrganizeArtistModalContentProps {
  artistIds: number[];
  onModalClose: () => void;
}

function OrganizeArtistModalContent(props: OrganizeArtistModalContentProps) {
  const { artistIds, onModalClose } = props;

  const allArtists: Artist[] = useSelector(createAllArtistSelector());

  const artistNames = useMemo(() => {
    const artists = artistIds.reduce((acc: Artist[], id) => {
      const a = allArtists.find((a) => a.id === id);

      if (a) {
        acc.push(a);
      }

      return acc;
    }, []);

    const sorted = orderBy(artists, ['sortName']);

    return sorted.map((a) => a.artistName);
  }, [artistIds, allArtists]);

  const onOrganizePress = useCallback(() => {
    // Call FastAPI rename command endpoint
    const promise = createAjaxRequest({
      url: '/api/artists/command/rename',
      method: 'POST',
      data: JSON.stringify({
        artist_ids: artistIds,
      }),
      dataType: 'json',
    }).request;

    promise.done(() => {
      onModalClose();
    });

    promise.fail((xhr) => {
      console.error('Failed to execute rename command:', xhr);
    });
  }, [artistIds, onModalClose]);

  return (
    <ModalContent onModalClose={onModalClose}>
      <ModalHeader>{translate('OrganizeSelectedArtists')}</ModalHeader>

      <ModalBody>
        <Alert>
          Tip: To preview a rename, select "Cancel", then select any artist name
          and use the
          <Icon className={styles.renameIcon} name={icons.ORGANIZE} />
        </Alert>

        <div className={styles.message}>
          Are you sure you want to organize all files in the{' '}
          {artistNames.length} selected artist?
        </div>

        <ul>
          {artistNames.map((artistName) => {
            return <li key={artistName}>{artistName}</li>;
          })}
        </ul>
      </ModalBody>

      <ModalFooter>
        <Button onPress={onModalClose}>{translate('Cancel')}</Button>

        <Button kind={kinds.DANGER} onPress={onOrganizePress}>
          {translate('Organize')}
        </Button>
      </ModalFooter>
    </ModalContent>
  );
}

export default OrganizeArtistModalContent;
